import { spawnSync } from 'node:child_process';
import {
  constants,
  openSync,
  closeSync,
  fstatSync,
  lstatSync,
  readFileSync,
} from 'node:fs';
import { join } from 'node:path';

import {
  computeReviewCandidate,
  REVIEW_SEVERITIES,
  REVIEW_STAGES,
  REVIEW_VERDICTS,
} from './review-candidate.mjs';
import { readState } from './state-loader.mjs';

const SHA256 = /^sha256:[a-f0-9]{64}$/;
const GIT_COMMIT = /^[a-f0-9]{40}$/;
const MAX_RESULT_BYTES = 64 * 1024;
const RESULT_FIELDS = [
  'stage',
  'candidate_identity',
  'verdict',
  'findings',
  'questions',
  'review_focus',
  'summary',
  'residual_risks',
];
const FINDING_FIELDS = [
  'severity',
  'file',
  'line',
  'impact',
  'suggested_repair',
];

export function parseCurrentReview(content, options = {}) {
  const bytes = Buffer.isBuffer(content) ? content : Buffer.from(content, 'utf8');
  if (bytes.length === 0 || bytes.length > MAX_RESULT_BYTES) {
    throw new Error('Current review result size is invalid');
  }
  let text;
  try {
    text = new TextDecoder('utf-8', { fatal: true }).decode(bytes);
  } catch {
    throw new Error('Current review result must be valid UTF-8');
  }
  let value;
  try {
    value = JSON.parse(text);
  } catch {
    throw new Error('Current review result is not valid JSON');
  }
  return validateCurrentReview(value, options);
}

export function validateCurrentReview(value, {
  expectedStage,
  expectedIdentity,
  expectedBase,
  allowedFindingPaths,
} = {}) {
  requirePlainObject(value, 'Current review result');
  if (!REVIEW_STAGES.includes(value.stage)) {
    throw new Error('Current review stage is invalid');
  }
  requireExactKeys(
    value,
    value.stage === 'final' ? [...RESULT_FIELDS, 'review_base'] : RESULT_FIELDS,
    'Current review result',
  );
  if (expectedStage && value.stage !== expectedStage) {
    throw new Error(`Current review stage must be ${expectedStage}`);
  }
  if (!SHA256.test(value.candidate_identity)) {
    throw new Error('Current review candidate identity is invalid');
  }
  if (expectedIdentity && value.candidate_identity !== expectedIdentity) {
    throw new Error('Current review candidate identity does not match current content');
  }
  if (!REVIEW_VERDICTS.includes(value.verdict)) {
    throw new Error('Current review verdict is invalid');
  }
  if (value.stage === 'final') {
    if (!GIT_COMMIT.test(value.review_base)) {
      throw new Error('Current final review base is invalid');
    }
    if (expectedBase && value.review_base !== expectedBase) {
      throw new Error('Current final review base does not match the requested review base');
    }
  }

  requireArray(value.findings, 'findings', 100);
  const allowed = allowedFindingPaths ? new Set(allowedFindingPaths) : null;
  value.findings.forEach((finding, index) => validateFinding(finding, index, allowed));
  requireTextArray(value.questions, 'questions', 20);
  requireTextArray(value.review_focus, 'review_focus', 20);
  requireText(value.summary, 'summary');
  requireTextArray(value.residual_risks, 'residual_risks', 20);

  const blocking = value.findings.filter(finding => finding.severity !== 'Low');
  if (value.verdict === 'Approved' && blocking.length > 0) {
    throw new Error('Approved current review must not contain a blocking finding');
  }
  if (value.verdict === 'Approved' && value.questions.length > 0) {
    throw new Error('Approved current review must not contain unresolved questions');
  }
  if (
    value.verdict === 'Request Changes'
    && blocking.length === 0
    && value.questions.length === 0
  ) {
    throw new Error('Request Changes requires a blocking finding or question');
  }
  return value;
}

export function currentReviewRelativePath(stage) {
  requireReviewStage(stage);
  return `reviews/${stage}-current.json`;
}

export function pendingReviewReportRelativePath(stage) {
  requireReviewStage(stage);
  return `reviews/${stage}-pending-report.json`;
}

export function checkCurrentReview({
  changeDir,
  stage,
  repoRoot,
  base,
  computeCandidate = computeReviewCandidate,
}) {
  try {
    requireReviewStage(stage);
    const effectiveRepoRoot = repoRoot ?? (
      stage === 'final' ? findRepositoryRoot(changeDir) : undefined
    );
    const prerequisiteIdentities = requireReviewStagePrerequisites({
      changeDir,
      stage,
      repoRoot: effectiveRepoRoot,
    });
    const currentPath = join(changeDir, currentReviewRelativePath(stage));
    let bytes;
    try {
      bytes = readRegularFileNoFollow(currentPath, 'Current review result');
    } catch (error) {
      if (error.code === 'ENOENT') return failure('missing', `Current ${stage} review is missing`);
      return failure('invalid', error.message);
    }

    const requestedBase = stage === 'final'
      ? resolveFinalReviewBase(changeDir, base)
      : base;
    const candidate = computeCandidate({
      changeDir,
      stage,
      repoRoot: effectiveRepoRoot,
      base: requestedBase,
      prerequisiteIdentities,
    });
    let review;
    try {
      review = parseCurrentReview(bytes, {
        expectedStage: stage,
        expectedIdentity: candidate.identity,
        expectedBase: candidate.review_base,
        allowedFindingPaths: candidate.allowed_finding_paths,
      });
    } catch (error) {
      const code = /identity does not match|base does not match/i.test(error.message)
        ? 'stale'
        : 'invalid';
      return failure(code, error.message, candidate.identity);
    }
    if (review.verdict !== 'Approved') {
      return failure('request-changes', `Current ${stage} review requested changes`, candidate.identity);
    }
    return {
      pass: true,
      code: 'approved',
      failures: [],
      candidate_identity: candidate.identity,
      review,
    };
  } catch (error) {
    return failure('prerequisite', error.message);
  }
}

export function resolveFinalReviewBase(changeDir, requestedBase) {
  if (requestedBase) return requestedBase;
  const recordedBase = readState(changeDir).execution_base_commit;
  if (!GIT_COMMIT.test(recordedBase ?? '')) {
    throw new Error('Final review requires an execution_base_commit recorded when the Change first entered executing');
  }
  return recordedBase;
}

export function requireReviewStagePrerequisites({ changeDir, stage, repoRoot }) {
  requireReviewStage(stage);
  const prerequisite = stage === 'design-tasks'
    ? { stage: 'proposal-specs', decision: 1 }
    : stage === 'final'
      ? { stage: 'design-tasks', decision: 2 }
      : null;
  if (!prerequisite) return {};

  const upstream = checkCurrentReview({
    changeDir,
    stage: prerequisite.stage,
    repoRoot,
  });
  if (!upstream.pass) {
    throw new Error(
      `Current ${prerequisite.stage} approval is required: ${upstream.failures.join('; ')}`,
    );
  }
  const state = readState(changeDir);
  const result = state[`dp_${prerequisite.decision}_result`];
  const identity = state[`dp_${prerequisite.decision}_candidate_identity`];
  if (result === null || result === undefined || result === '') {
    throw new Error(`DP-${prerequisite.decision} result is required`);
  }
  if (identity !== upstream.candidate_identity) {
    throw new Error(
      `DP-${prerequisite.decision} candidate identity must match current ${prerequisite.stage} approval`,
    );
  }
  if (stage === 'design-tasks') {
    return {
      'proposal-specs': upstream.candidate_identity,
    };
  }
  return {
    'proposal-specs': state.dp_1_candidate_identity,
    'design-tasks': upstream.candidate_identity,
  };
}

export function readRegularFileNoFollow(path, label, {
  noFollowFlag = constants.O_NOFOLLOW ?? 0,
} = {}) {
  const before = lstatSync(path);
  if (before.isSymbolicLink() || !before.isFile()) {
    throw new Error(`${label} must be a regular file, not a symbolic link`);
  }
  const noFollow = noFollowFlag;
  const descriptor = openSync(path, constants.O_RDONLY | noFollow);
  try {
    const stat = fstatSync(descriptor);
    if (!stat.isFile()) throw new Error(`${label} must be a regular file`);
    const after = lstatSync(path);
    if (
      after.isSymbolicLink()
      || !after.isFile()
      || before.dev !== stat.dev
      || before.ino !== stat.ino
      || after.dev !== stat.dev
      || after.ino !== stat.ino
    ) {
      throw new Error(`${label} changed while it was opened`);
    }
    if (typeof process.getuid === 'function' && stat.uid !== process.getuid()) {
      throw new Error(`${label} must be owned by the current user`);
    }
    return readFileSync(descriptor);
  } finally {
    closeSync(descriptor);
  }
}

function validateFinding(finding, index, allowedPaths) {
  const label = `finding ${index + 1}`;
  requirePlainObject(finding, label);
  requireExactKeys(finding, FINDING_FIELDS, label);
  if (!REVIEW_SEVERITIES.includes(finding.severity)) {
    throw new Error(`${label} severity is invalid`);
  }
  requireRepositoryPath(finding.file, `${label} file`);
  if (allowedPaths && !allowedPaths.has(finding.file)) {
    throw new Error(`${label} file is outside the allowed finding paths`);
  }
  if (!Number.isInteger(finding.line) || finding.line < 1) {
    throw new Error(`${label} line is invalid`);
  }
  requireText(finding.impact, `${label} impact`);
  requireText(finding.suggested_repair, `${label} suggested_repair`);
}

function requireReviewStage(stage) {
  if (!REVIEW_STAGES.includes(stage)) throw new Error(`Unsupported review stage: ${stage}`);
}

function requirePlainObject(value, label) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
}

function requireExactKeys(value, expected, label) {
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  if (JSON.stringify(actual) !== JSON.stringify(wanted)) {
    throw new Error(`${label} fields are invalid`);
  }
}

function requireArray(value, label, maximum) {
  if (!Array.isArray(value) || value.length > maximum) {
    throw new Error(`${label} must be an array with at most ${maximum} entries`);
  }
}

function requireText(value, label) {
  if (typeof value !== 'string' || value.trim() === '') {
    throw new Error(`${label} must be non-empty text`);
  }
}

function requireTextArray(value, label, maximum) {
  requireArray(value, label, maximum);
  value.forEach((entry, index) => requireText(entry, `${label} ${index + 1}`));
}

function requireRepositoryPath(path, label) {
  requireText(path, label);
  if (
    path.startsWith('/')
    || path.includes('\\')
    || path.split('/').some(part => part === '..' || part === '.' || part === '')
    || /[\u0000-\u001f]/.test(path)
  ) {
    throw new Error(`${label} must be a normalized repository-relative path`);
  }
}

function failure(code, message, candidateIdentity = null) {
  return {
    pass: false,
    code,
    failures: [message],
    candidate_identity: candidateIdentity,
  };
}

function findRepositoryRoot(changeDir) {
  const result = spawnSync('git', ['-C', changeDir, 'rev-parse', '--show-toplevel'], {
    encoding: 'utf8',
  });
  if (result.status !== 0) {
    throw new Error('Final review Change must be inside a Git repository');
  }
  return result.stdout.trim();
}
