import { checkCurrentReview } from '../../lib/review-evidence.mjs';
import { readState } from '../../lib/state-loader.mjs';

export function checkProposalSpecsReviewApproved(changeDir) {
  return checkCurrentReview({ changeDir, stage: 'proposal-specs' });
}

export function checkDesignTasksReviewApproved(changeDir) {
  return checkCurrentReview({ changeDir, stage: 'design-tasks' });
}

export function checkFinalReviewApproved(changeDir) {
  return checkCurrentReview({ changeDir, stage: 'final' });
}

export function checkReviewApproved(changeDir, fromState, toState) {
  const transition = `${fromState}:${toState}`;
  if (transition === 'specifying:bridging') {
    const state = readState(changeDir);
    const proposal = checkProposalSpecsReviewApproved(changeDir);
    const design = checkDesignTasksReviewApproved(changeDir);
    const failures = [
      ...proposal.failures,
      ...design.failures,
    ];
    for (const [field, label] of [
      ['dp_1_result', 'DP-1 result'],
      ['dp_1_candidate_identity', 'DP-1 candidate identity'],
      ['dp_2_result', 'DP-2 result'],
      ['dp_2_candidate_identity', 'DP-2 candidate identity'],
    ]) {
      if (!state[field]) failures.push(`${label} is not recorded`);
    }
    if (proposal.pass && state.dp_1_candidate_identity !== proposal.candidate_identity) {
      failures.push('DP-1 candidate identity does not match the current Proposal/Specs approval');
    }
    if (design.pass && state.dp_2_candidate_identity !== design.candidate_identity) {
      failures.push('DP-2 candidate identity does not match the current Design/Tasks approval');
    }
    return {
      pass: failures.length === 0,
      failures,
    };
  }
  if (transition === 'executing:closing') {
    return checkFinalReviewApproved(changeDir);
  }
  return { pass: true, failures: [] };
}
