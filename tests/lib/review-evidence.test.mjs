import assert from 'node:assert/strict';
import {
  mkdirSync,
  mkdtempSync,
  rmSync,
  symlinkSync,
  writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, it } from 'node:test';

import {
  checkCurrentReview,
  currentReviewRelativePath,
  parseCurrentReview,
  readRegularFileNoFollow,
} from '../../scripts/lib/review-evidence.mjs';

const IDENTITY = `sha256:${'a'.repeat(64)}`;

function report(overrides = {}) {
  return {
    stage: 'proposal-specs',
    candidate_identity: IDENTITY,
    verdict: 'Approved',
    findings: [],
    questions: [],
    review_focus: ['scope', 'behavior'],
    summary: 'The current Proposal and Specs are coherent.',
    residual_risks: ['Real host execution remains separate.'],
    ...overrides,
  };
}

describe('minimal typed review evidence', () => {
  it('accepts the typed verdict and rejects removed protocol fields', () => {
    assert.deepEqual(
      parseCurrentReview(JSON.stringify(report()), {
        expectedStage: 'proposal-specs',
        expectedIdentity: IDENTITY,
        allowedFindingPaths: ['proposal.md'],
      }),
      report(),
    );
    assert.throws(
      () => parseCurrentReview(JSON.stringify({
        ...report(),
        handoff_attestation: `sha256:${'b'.repeat(64)}`,
      })),
      /field|key|handoff/i,
    );
  });

  it('enforces verdict consistency and stage finding allowlists', () => {
    const finding = {
      severity: 'High',
      file: 'proposal.md',
      line: 4,
      impact: 'A required behavior can be omitted.',
      suggested_repair: 'State the behavior explicitly.',
    };
    assert.throws(
      () => parseCurrentReview(JSON.stringify(report({ findings: [finding] }))),
      /Approved.*finding|blocking/i,
    );
    assert.throws(
      () => parseCurrentReview(JSON.stringify(report({
        verdict: 'Request Changes',
      }))),
      /Request Changes.*finding|question/i,
    );
    assert.throws(
      () => parseCurrentReview(JSON.stringify(report({
        verdict: 'Request Changes',
        findings: [{ ...finding, file: 'design.md' }],
      })), {
        expectedStage: 'proposal-specs',
        expectedIdentity: IDENTITY,
        allowedFindingPaths: ['proposal.md'],
      }),
      /outside|allowed/i,
    );
    assert.equal(
      parseCurrentReview(JSON.stringify(report({
        verdict: 'Request Changes',
        findings: [finding],
      })), {
        expectedStage: 'proposal-specs',
        expectedIdentity: IDENTITY,
        allowedFindingPaths: ['proposal.md'],
      }).verdict,
      'Request Changes',
    );
  });

  it('requires every finding line to be a positive integer', () => {
    const finding = {
      severity: 'High',
      file: 'proposal.md',
      line: 4,
      impact: 'A required behavior can be omitted.',
      suggested_repair: 'State the behavior explicitly.',
    };
    const parseFinding = line => parseCurrentReview(JSON.stringify(report({
      verdict: 'Request Changes',
      findings: [{ ...finding, line }],
    })), {
      expectedStage: 'proposal-specs',
      expectedIdentity: IDENTITY,
      allowedFindingPaths: ['proposal.md'],
    });

    for (const invalidLine of [null, 0, -1, 1.5, '1']) {
      assert.throws(() => parseFinding(invalidLine), /finding 1 line is invalid/i);
    }
    assert.equal(parseFinding(1).findings[0].line, 1);
  });

  it('uses one fixed current-result path per stage', () => {
    assert.equal(currentReviewRelativePath('proposal-specs'), 'reviews/proposal-specs-current.json');
    assert.equal(currentReviewRelativePath('design-tasks'), 'reviews/design-tasks-current.json');
    assert.equal(currentReviewRelativePath('final'), 'reviews/final-current.json');
    assert.throws(() => currentReviewRelativePath('../escape'), /stage/i);
  });

  it('rejects a symlink when the platform has no O_NOFOLLOW flag', () => {
    const root = mkdtempSync(join(tmpdir(), 'ssf-review-no-nofollow-'));
    try {
      const target = join(root, 'target.json');
      const inbox = join(root, 'pending.json');
      writeFileSync(target, '{}\n');
      symlinkSync(target, inbox);

      assert.throws(
        () => readRegularFileNoFollow(inbox, 'Pending review report', {
          noFollowFlag: 0,
        }),
        /regular file|symbolic link/i,
      );
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it('fails closed for missing, Request Changes, and stale current results', () => {
    const root = mkdtempSync(join(tmpdir(), 'ssf-review-evidence-'));
    try {
      const candidate = {
        stage: 'proposal-specs',
        identity: IDENTITY,
        allowed_finding_paths: ['proposal.md'],
      };
      const computeCandidate = () => candidate;
      let checked = checkCurrentReview({
        changeDir: root,
        stage: 'proposal-specs',
        computeCandidate,
      });
      assert.equal(checked.pass, false);
      assert.equal(checked.code, 'missing');

      const reviews = join(root, 'reviews');
      mkdirSync(reviews);
      writeFileSync(
        join(reviews, 'proposal-specs-current.json'),
        `${JSON.stringify(report({
          verdict: 'Request Changes',
          findings: [{
            severity: 'High',
            file: 'proposal.md',
            line: 1,
            impact: 'Scope is incomplete.',
            suggested_repair: 'Repair scope.',
          }],
        }))}\n`,
      );
      checked = checkCurrentReview({
        changeDir: root,
        stage: 'proposal-specs',
        computeCandidate,
      });
      assert.equal(checked.pass, false);
      assert.equal(checked.code, 'request-changes');

      writeFileSync(
        join(reviews, 'proposal-specs-current.json'),
        `${JSON.stringify(report({ candidate_identity: `sha256:${'b'.repeat(64)}` }))}\n`,
      );
      checked = checkCurrentReview({
        changeDir: root,
        stage: 'proposal-specs',
        computeCandidate,
      });
      assert.equal(checked.pass, false);
      assert.equal(checked.code, 'stale');
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });
});
