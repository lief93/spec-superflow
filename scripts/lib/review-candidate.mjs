import { createHash } from 'node:crypto';
import {
  readFileSync,
  readdirSync,
  statSync,
} from 'node:fs';
import { join, relative, resolve, sep } from 'node:path';

import { collectWorktreeReviewCandidate } from './worktree-review-candidate.mjs';

export const REVIEW_STAGES = ['proposal-specs', 'design-tasks', 'final'];
export const REVIEW_VERDICTS = ['Approved', 'Request Changes'];
export const REVIEW_SEVERITIES = ['Critical', 'High', 'Medium', 'Low'];

const FINAL_INPUTS = [
  'user-intent.md',
  'execution-contract.md',
  'pr-summary.md',
  'known-risks.md',
  'runtime-evidence.md',
];
const FINAL_LOCAL_TARGETS = [
  'pr-summary.md',
  'known-risks.md',
  'runtime-evidence.md',
];
const SHA256_IDENTITY = /^sha256:[a-f0-9]{64}$/;

export function computeReviewCandidate({
  changeDir,
  stage,
  repoRoot,
  base,
  prerequisiteIdentities,
}) {
  requireReviewStage(stage);
  const changePath = resolve(changeDir);
  if (!statSync(changePath).isDirectory()) {
    throw new Error('Change path must be a directory');
  }

  const inputs = stageInputs(changePath, stage);
  const hash = createHash('sha256');
  hash.update(`spec-superflow-review-candidate-v3\0${stage}\0`, 'utf8');
  for (const relativePath of inputs) {
    const content = readFileSync(join(changePath, relativePath));
    const semanticContent = relativePath === 'tasks.md'
      ? Buffer.from(normalizeTaskCompletionMarkers(content.toString('utf8')), 'utf8')
      : content;
    updateFramed(hash, relativePath, semanticContent);
  }

  const upstreamCandidateIdentities = requirePrerequisiteIdentities(
    stage,
    prerequisiteIdentities,
  );
  for (const [upstreamStage, identity] of Object.entries(upstreamCandidateIdentities)) {
    updateFramed(
      hash,
      `upstream/${upstreamStage}-candidate-identity`,
      Buffer.from(identity, 'utf8'),
    );
  }

  let worktree = null;
  if (stage === 'final') {
    if (!repoRoot || !base) {
      throw new Error('Final review candidate requires a repository root and review base');
    }
    worktree = collectWorktreeReviewCandidate({ repoRoot, changeDir: changePath, base });
    updateFramed(hash, 'git/review-base', Buffer.from(worktree.reviewBase, 'utf8'));
    updateFramed(hash, 'git/worktree-identity', Buffer.from(worktree.identity, 'utf8'));
  }

  const reviewTargets = stageReviewTargets(stage, inputs, worktree);
  return {
    stage,
    identity: `sha256:${hash.digest('hex')}`,
    inputs,
    review_targets: reviewTargets,
    allowed_finding_paths: reviewTargets,
    ...(Object.keys(upstreamCandidateIdentities).length > 0
      ? { upstream_candidate_identities: upstreamCandidateIdentities }
      : {}),
    ...(worktree ? {
      review_base: worktree.reviewBase,
      worktree_identity: worktree.identity,
      changed_files: worktree.changedFiles,
    } : {}),
  };
}

function requirePrerequisiteIdentities(stage, prerequisiteIdentities) {
  const required = stage === 'design-tasks'
    ? ['proposal-specs']
    : stage === 'final'
      ? ['proposal-specs', 'design-tasks']
      : [];
  const identities = {};
  for (const upstreamStage of required) {
    const identity = prerequisiteIdentities?.[upstreamStage];
    if (!SHA256_IDENTITY.test(identity ?? '')) {
      throw new Error(
        `${stage} review candidate requires current Approved ${upstreamStage} candidate identity`,
      );
    }
    identities[upstreamStage] = identity;
  }
  return identities;
}

export function normalizeTaskCompletionMarkers(content) {
  const output = [];
  let fence = null;
  for (const line of content.split('\n')) {
    const marker = line.match(/^( {0,3})(`{3,}|~{3,})(.*)$/);
    if (fence) {
      output.push(line);
      if (
        marker
        && marker[2][0] === fence.character
        && marker[2].length >= fence.length
        && marker[3].trim() === ''
      ) {
        fence = null;
      }
      continue;
    }
    if (marker) {
      fence = { character: marker[2][0], length: marker[2].length };
      output.push(line);
      continue;
    }
    output.push(line.replace(/^( {0,3}- )\[[ xX]\]/, '$1[ ]'));
  }
  return output.join('\n');
}

function stageInputs(changePath, stage) {
  if (stage === 'proposal-specs') {
    return [
      'user-intent.md',
      'proposal.md',
      ...listDeltaSpecs(changePath),
    ];
  }
  if (stage === 'design-tasks') return ['design.md', 'tasks.md'];
  return [...FINAL_INPUTS];
}

function stageReviewTargets(stage, inputs, worktree) {
  if (stage === 'proposal-specs') return inputs.filter(path => path !== 'user-intent.md');
  if (stage === 'design-tasks') return [...inputs];
  return uniqueSorted([
    ...worktree.changedFiles.map(file => file.path),
    ...FINAL_LOCAL_TARGETS,
  ]);
}

function listDeltaSpecs(changePath) {
  const specsRoot = join(changePath, 'specs');
  if (!statSync(specsRoot).isDirectory()) {
    throw new Error('Proposal and Specs review requires a specs directory');
  }
  const files = [];
  walk(specsRoot, files);
  const relativeFiles = files
    .map(path => toPosix(relative(changePath, path)))
    .filter(path => /(?:^|\/)spec\.md$/.test(path));
  if (relativeFiles.length === 0) {
    throw new Error('Proposal and Specs review requires at least one delta spec');
  }
  return relativeFiles.sort(compareUtf8);
}

function walk(directory, files) {
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) walk(path, files);
    else if (entry.isFile()) files.push(path);
  }
}

function updateFramed(hash, label, content) {
  hash.update(`${Buffer.byteLength(label)}:${label}:${content.length}:`, 'utf8');
  hash.update(content);
}

function requireReviewStage(stage) {
  if (!REVIEW_STAGES.includes(stage)) {
    throw new Error(`Unsupported review stage: ${stage}`);
  }
}

function uniqueSorted(values) {
  return [...new Set(values)].sort(compareUtf8);
}

function compareUtf8(left, right) {
  return Buffer.compare(Buffer.from(left), Buffer.from(right));
}

function toPosix(path) {
  return sep === '/' ? path : path.split(sep).join('/');
}
