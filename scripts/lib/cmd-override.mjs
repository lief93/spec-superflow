import {
  existsSync,
  lstatSync,
  readdirSync,
  realpathSync,
  rmSync,
  writeFileSync,
} from 'node:fs';
import { spawnSync } from 'node:child_process';
import { basename, join, sep } from 'node:path';
import { parseArgs } from 'node:util';

import {
  appendDeveloperOverride,
  requireChangeDirectory,
  writeDeveloperWaiver,
} from './developer-override.mjs';
import { computeArtifactsHash, computeContractHash } from './hash.mjs';
import { computeReviewCandidate, REVIEW_STAGES } from './review-candidate.mjs';
import {
  checkCurrentReview,
  requireReviewStagePrerequisites,
  resolveFinalReviewBase,
} from './review-evidence.mjs';
import { readState, writeState } from './state-loader.mjs';

const COMMANDS = [
  'waive-review',
  'continue-review',
  'light-replan',
  'resume-check',
  'rewind',
  'abandon',
];
const REWIND_TARGETS = ['exploring', 'specifying', 'bridging', 'approved-for-build'];
const STATE_ORDER = [
  'exploring',
  'specifying',
  'bridging',
  'approved-for-build',
  'executing',
  'debugging',
  'closing',
];

export function run(args) {
  const { positionals, values } = parseArgs({
    args,
    options: {
      reason: { type: 'string' },
      json: { type: 'boolean', default: false },
    },
    allowPositionals: true,
  });
  const [action, requestedChangeDir, argument] = positionals;
  if (
    !COMMANDS.includes(action)
    || !requestedChangeDir
    || (action !== 'resume-check' && !values.reason?.trim())
  ) {
    printUsage();
    process.exit(2);
  }

  const changeDir = requireChangeDirectory(requestedChangeDir);
  const timestamp = new Date().toISOString();
  const common = {
    action,
    actor: 'developer',
    reason: values.reason?.trim(),
    timestamp,
  };
  let result;

  if (action === 'waive-review') {
    result = waiveReview(changeDir, argument, common);
  } else if (action === 'continue-review') {
    result = continueReview(changeDir, argument, common);
  } else if (action === 'light-replan') {
    if (argument) return usageError();
    result = lightReplan(changeDir, common);
  } else if (action === 'resume-check') {
    if (argument || values.reason) return usageError();
    const result = checkResume(changeDir);
    printResult(result, values.json);
    if (!result.ready) process.exit(1);
    return;
  } else if (action === 'rewind') {
    result = rewind(changeDir, argument, common);
  } else {
    if (argument) return usageError();
    result = abandon(changeDir, common);
  }

  appendDeveloperOverride(changeDir, result.audit);
  printResult(result.output, values.json);
}

function checkResume(changeDir) {
  const state = readState(changeDir);
  const currentArtifactsHash = computeArtifactsHash(changeDir);
  const currentContractHash = computeContractHash(changeDir);
  const failures = [];
  if (state.state !== 'executing') failures.push('Workflow state must be executing');
  if (!state.artifacts_hash || state.artifacts_hash !== currentArtifactsHash) {
    failures.push('Planning lock is missing or stale');
  }
  if (!state.contract_hash || state.contract_hash !== currentContractHash) {
    failures.push('Contract lock is missing or stale');
  }
  if (state.workflow === 'full') {
    const proposalReview = checkCurrentReview({ changeDir, stage: 'proposal-specs' });
    if (!proposalReview.pass) {
      failures.push(`Current Proposal/Specs review or developer waiver is missing: ${proposalReview.failures.join('; ')}`);
    } else if (
      !state.dp_1_result
      || state.dp_1_candidate_identity !== proposalReview.candidate_identity
    ) {
      failures.push('DP-1 must be bound to the current Proposal/Specs review or developer waiver');
    }
    const designReview = checkCurrentReview({ changeDir, stage: 'design-tasks' });
    if (!designReview.pass) {
      failures.push(`Current Design/Tasks review or developer waiver is missing: ${designReview.failures.join('; ')}`);
    } else if (
      !state.dp_2_result
      || state.dp_2_candidate_identity !== designReview.candidate_identity
    ) {
      failures.push('DP-2 must be bound to the current Design/Tasks review or developer waiver');
    }
  }
  if (!state.dp_3_result) failures.push('DP-3 refreshed contract approval is missing');
  if (!state.dp_4_result) failures.push('DP-4 refreshed execution mode is missing');
  return {
    ready: failures.length === 0,
    state: state.state,
    failures,
  };
}

function lightReplan(changeDir, common) {
  const state = readState(changeDir);
  if (state.state !== 'executing' && state.state !== 'debugging') {
    throw new Error('Light replan is available only during executing or debugging');
  }
  const from = state.state;
  state.state = 'executing';
  for (let decision = 1; decision <= 7; decision += 1) {
    state[`dp_${decision}_result`] = null;
    state[`dp_${decision}_timestamp`] = null;
    if (decision === 1 || decision === 2) {
      state[`dp_${decision}_candidate_identity`] = null;
    }
  }
  state.artifacts_hash = null;
  state.contract_hash = null;
  state.test_result = null;
  state.last_transition_from = from;
  state.last_transition_to = 'executing';
  state.last_transition = common.timestamp;
  removeDownstreamReviewEvidence(changeDir, 'specifying');
  writeState(changeDir, state);
  const record = { ...common, from, to: 'executing' };
  return {
    audit: record,
    output: { ok: true, ...record },
  };
}

function waiveReview(changeDir, stage, common) {
  requireReviewStage(stage);
  const repoRoot = stage === 'final' ? findRepositoryRoot(changeDir) : process.cwd();
  const prerequisiteIdentities = requireReviewStagePrerequisites({
    changeDir,
    stage,
    repoRoot,
  });
  const base = stage === 'final' ? resolveFinalReviewBase(changeDir) : undefined;
  const candidate = computeReviewCandidate({
    changeDir,
    stage,
    repoRoot,
    base,
    prerequisiteIdentities,
  });
  const waiver = {
    ...common,
    stage,
    candidate_identity: candidate.identity,
  };
  const path = writeDeveloperWaiver(changeDir, waiver);
  return {
    audit: { ...waiver, path },
    output: { ok: true, ...waiver, path },
  };
}

function continueReview(changeDir, stage, common) {
  requireReviewStage(stage);
  const record = { ...common, stage };
  return {
    audit: record,
    output: { ok: true, ...record, state: readState(changeDir).state },
  };
}

function rewind(changeDir, target, common) {
  if (!REWIND_TARGETS.includes(target)) {
    throw new Error(`Rewind target must be one of: ${REWIND_TARGETS.join(', ')}`);
  }
  const state = readState(changeDir);
  if (state.state === 'abandoned' || state.state === 'closing') {
    throw new Error(`Cannot rewind terminal state ${state.state}`);
  }
  if (state.state === 'debugging') state.state = 'executing';
  if (STATE_ORDER.indexOf(target) >= STATE_ORDER.indexOf(state.state)) {
    throw new Error(`Rewind target ${target} must be earlier than current state ${state.state}`);
  }

  const from = state.state;
  invalidateStateForTarget(state, target, changeDir);
  removeDownstreamReviewEvidence(changeDir, target);
  state.state = target;
  state.last_transition_from = from;
  state.last_transition_to = target;
  state.last_transition = common.timestamp;
  writeState(changeDir, state);

  const record = { ...common, from, to: target };
  return {
    audit: record,
    output: { ok: true, ...record },
  };
}

function abandon(changeDir, common) {
  const state = readState(changeDir);
  if (state.state === 'closing' || state.state === 'abandoned') {
    throw new Error(`Cannot abandon terminal state ${state.state}`);
  }
  const from = state.state;
  writeFileSync(join(changeDir, 'abandonment-summary.md'), `# Abandonment Summary

## Change

- **Name**: ${state.change_name ?? basename(changeDir)}
- **Original goal**: See \`user-intent.md\` and \`proposal.md\`.

## Reason

${common.reason}

## What Was Tried

- Work completed before abandonment remains in the Change directory and Git history.

## Lessons Learned

- Review the preserved artifacts before restarting or replacing this Change.

## Recommendations

- Start a new Change or explicitly rewind this work if the requirement returns.

## Preserved Work

- [x] Partial work preserved in the current Change directory.
`);
  state.state = 'abandoned';
  state.last_transition_from = from;
  state.last_transition_to = 'abandoned';
  state.last_transition = common.timestamp;
  writeState(changeDir, state);
  const record = { ...common, from, to: 'abandoned' };
  return {
    audit: record,
    output: { ok: true, ...record },
  };
}

function invalidateStateForTarget(state, target, changeDir) {
  const firstDecision = target === 'exploring'
    ? 0
    : target === 'specifying'
      ? 1
      : target === 'bridging'
        ? 3
        : 4;
  for (let decision = firstDecision; decision <= 7; decision += 1) {
    state[`dp_${decision}_result`] = null;
    state[`dp_${decision}_timestamp`] = null;
    if (decision <= 2) {
      state[`dp_${decision}_decisions`] = null;
      state[`dp_${decision}_confirmed`] = null;
    }
    if (decision === 1 || decision === 2) {
      state[`dp_${decision}_candidate_identity`] = null;
    }
  }
  state.batches_completed = 0;
  state.test_result = null;
  if (target === 'exploring' || target === 'specifying' || target === 'bridging') {
    state.artifacts_hash = null;
    state.contract_hash = null;
  } else {
    state.artifacts_hash = computeArtifactsHash(changeDir);
    state.contract_hash = computeContractHash(changeDir);
  }
}

function removeDownstreamReviewEvidence(changeDir, target) {
  const stages = target === 'bridging' || target === 'approved-for-build'
    ? ['final']
    : REVIEW_STAGES;
  const reviews = join(changeDir, 'reviews');
  if (!existsSync(reviews)) return;
  const stat = lstatSync(reviews);
  if (stat.isSymbolicLink() || !stat.isDirectory()) {
    throw new Error('reviews must be a real directory');
  }
  const canonicalReviews = realpathSync(reviews);
  if (!canonicalReviews.startsWith(`${realpathSync(changeDir)}${sep}`)) {
    throw new Error('reviews directory escapes the Change directory');
  }
  for (const entry of readdirSync(canonicalReviews, { withFileTypes: true })) {
    if (!entry.isFile() || entry.isSymbolicLink()) continue;
    if (stages.some(stage => entry.name.startsWith(`${stage}-`))) {
      rmSync(join(canonicalReviews, entry.name), { force: true });
    }
  }
}

function requireReviewStage(stage) {
  if (!REVIEW_STAGES.includes(stage)) {
    throw new Error(`Unsupported review stage: ${stage}`);
  }
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

function printResult(result, json) {
  if (json) console.log(JSON.stringify(result));
  else if (result.ready !== undefined) {
    console.log(result.ready ? 'Execution resume ready.' : result.failures.join('; '));
  } else {
    console.log(`${result.action}: ${result.stage ?? result.to}`);
  }
}

function usageError() {
  printUsage();
  process.exit(2);
}

function printUsage() {
  console.error('Usage: ssf override waive-review <change-dir> <stage> --reason <text> [--json]');
  console.error('       ssf override continue-review <change-dir> <stage> --reason <text> [--json]');
  console.error('       ssf override light-replan <change-dir> --reason <text> [--json]');
  console.error('       ssf override resume-check <change-dir> [--json]');
  console.error('       ssf override rewind <change-dir> <earlier-state> --reason <text> [--json]');
  console.error('       ssf override abandon <change-dir> --reason <text> [--json]');
}
