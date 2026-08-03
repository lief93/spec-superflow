// tests/lib/guard-transitions.test.mjs
// Regression tests for state machine transition guard matrix
// Covers specs/guard-transitions/spec.md requirements

import { describe, it, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { execSync, spawnSync } from 'node:child_process';
import { mkdtempSync, writeFileSync, rmSync, mkdirSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { dirname } from 'node:path';
import { computeReviewCandidate } from '../../scripts/lib/review-candidate.mjs';
import { computeContractHash } from '../../scripts/lib/hash.mjs';
import { readState, writeState } from '../../scripts/lib/state-loader.mjs';
import { check as checkDpGate } from '../../scripts/guard/checks/dp-gate-passed.mjs';
import { checkReviewApproved } from '../../scripts/guard/checks/review-approved.mjs';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '..', '..');
const GUARD = join(ROOT, 'scripts', 'guard', 'guard.mjs');

// All legal transitions (from docs/state-machine.md)
const ALL_TRANSITIONS = [
  // Mainline
  { from: 'exploring', to: 'specifying' },
  { from: 'specifying', to: 'bridging' },
  { from: 'bridging', to: 'approved-for-build' },
  { from: 'approved-for-build', to: 'executing' },
  { from: 'executing', to: 'closing' },
  // Fast-path
  { from: 'exploring', to: 'bridging', workflow: 'hotfix' },
  { from: 'exploring', to: 'approved-for-build', workflow: 'tweak' },
  // Rewind
  { from: 'executing', to: 'specifying' },
  { from: 'executing', to: 'bridging' },
  { from: 'approved-for-build', to: 'specifying' },
  { from: 'approved-for-build', to: 'bridging' },
  { from: 'specifying', to: 'exploring' },
  { from: 'bridging', to: 'specifying' },
  // Debugging round-trip
  { from: 'executing', to: 'debugging' },
  { from: 'debugging', to: 'executing' },
  // Abandon
  { from: 'exploring', to: 'abandoned' },
  { from: 'specifying', to: 'abandoned' },
  { from: 'bridging', to: 'abandoned' },
  { from: 'approved-for-build', to: 'abandoned' },
  { from: 'executing', to: 'abandoned' },
  { from: 'debugging', to: 'abandoned' },
];

// Illegal transitions (should be rejected)
const ILLEGAL_TRANSITIONS = [
  { from: 'exploring', to: 'closing' },
  { from: 'exploring', to: 'executing' },
  { from: 'specifying', to: 'executing' },
  { from: 'specifying', to: 'closing' },
  { from: 'bridging', to: 'closing' },
  { from: 'closing', to: 'abandoned' },
  { from: 'abandoned', to: 'exploring' },
  { from: 'abandoned', to: 'specifying' },
];

function makeChangeDir() {
  const dir = mkdtempSync(join(tmpdir(), 'ssf-guard-test-'));
  mkdirSync(join(dir, 'specs'), { recursive: true });
  return dir;
}

function cleanup(dir) {
  if (existsSync(dir)) rmSync(dir, { recursive: true, force: true });
}

function runGuard(from, to, dir, workflow = 'full') {
  try {
    // Write a minimal .spec-superflow.yaml so guard can read state
    const stateFile = join(dir, '.spec-superflow.yaml');
    writeFileSync(stateFile, `state: ${from}\nworkflow: ${workflow}\nchange_name: test\n`);

    // Also need a minimal proposal.md for artifacts-exist check
    writeFileSync(join(dir, 'proposal.md'), '# Test\n\n## Why\n\nTest change for guard matrix audit.\n\n## What Changes\n\n- Test.\n');
    writeFileSync(join(dir, 'design.md'), '# Design\n\n## Context\n\nTest.\n\n## Goals\n\nTest.\n\n## Decisions\n\n### Decision 1\n- Choice: Test\n- Rationale: Test\n\n## Risks And Trade-Offs\n\nNone.\n');
    writeFileSync(join(dir, 'tasks.md'), '# Tasks\n\n- [x] Task 1\n- [x] Task 2\n');
    writeFileSync(join(dir, 'specs', 'test.md'), '## ADDED Requirements\n\n### Requirement: Test\n\nThe system SHALL test.\n\n#### Scenario: Test\n- **WHEN** test\n- **THEN** test\n');
    writeFileSync(join(dir, 'execution-contract.md'), '# Execution Contract\n\n## Intent Lock\n\nTest.\n');

    const cmd = `node ${GUARD} check "${dir}" ${from} ${to}`;
    if (workflow !== 'full') {
      execSync(`${cmd} --workflow ${workflow} --json`, { stdio: 'pipe', timeout: 5000 });
    } else {
      execSync(`${cmd} --json`, { stdio: 'pipe', timeout: 5000 });
    }
    return { ok: true };
  } catch (e) {
    return { ok: false, stderr: e.stderr?.toString() || e.message };
  }
}

// ─── D1: Guard 检查矩阵完整性 ───
// Requirement: Guard 检查矩阵完整性
// Scenario: 主线 transition 全覆盖

describe('Guard transition matrix completeness', () => {
  let dir;
  before(() => { dir = makeChangeDir(); });
  after(() => { cleanup(dir); });

  for (const t of ALL_TRANSITIONS) {
    const label = `${t.from} → ${t.to}${t.workflow ? ' (' + t.workflow + ')' : ''}`;
    it(`SHALL define checks for ${label}`, () => {
      const result = runGuard(t.from, t.to, dir, t.workflow || 'full');
      // The transition should be handled (either pass or fail with specific reason, but not "unknown transition")
      if (!result.ok) {
        assert.ok(
          !result.stderr.includes('unknown transition') && !result.stderr.includes('Unknown transition'),
          `Transition ${label} is not defined in guard matrix: ${result.stderr}`
        );
      }
    });
  }
});

// Requirement: Guard 检查矩阵完整性
// Scenario: 非法 transition 被拦截
describe('Illegal transition rejection', () => {
  let dir;
  before(() => { dir = makeChangeDir(); });
  after(() => { cleanup(dir); });

  for (const t of ILLEGAL_TRANSITIONS) {
    it(`SHALL reject illegal transition ${t.from} → ${t.to}`, () => {
      const result = runGuard(t.from, t.to, dir);
      assert.equal(result.ok, false, `Illegal transition ${t.from} → ${t.to} should be rejected`);
    });
  }
});

// Requirement: Guard 脚本错误处理
// Scenario: guard 脚本异常时报告给用户
describe('Guard error handling', () => {
  it('SHALL return non-zero exit when called without arguments', () => {
    try {
      execSync(`node ${GUARD} check`, { stdio: 'pipe', timeout: 5000 });
      assert.fail('Should have thrown');
    } catch (e) {
      assert.ok(e.status !== 0, 'Guard should exit non-zero for missing arguments');
    }
  });

  it('SHALL output error for nonexistent change directory', () => {
    try {
      execSync(`node ${GUARD} check /nonexistent/path exploring specifying`, { stdio: 'pipe', timeout: 5000 });
      assert.fail('Should have thrown');
    } catch (e) {
      assert.ok(e.status !== 0, 'Guard should exit non-zero for nonexistent directory');
    }
  });
});

// ─── D1: Debugging 状态往返 ───
// Requirement: Debugging 状态往返无副作用
// Scenario: debugging 返回 executing 后进度保留
describe('Debugging round-trip', () => {
  let dir;
  before(() => { dir = makeChangeDir(); });
  after(() => { cleanup(dir); });

  it('SHALL allow executing → debugging transition', () => {
    const result = runGuard('executing', 'debugging', dir);
    // The transition may fail due to missing execution artifacts, but should NOT be "unknown transition"
    if (!result.ok) {
      assert.ok(!result.stderr?.includes('unknown'), `Should not reject with unknown: ${result.stderr}`);
    }
  });

  it('SHALL allow debugging → executing transition', () => {
    const result = runGuard('debugging', 'executing', dir);
    if (!result.ok) {
      assert.ok(!result.stderr?.includes('unknown'), `Should not reject with unknown: ${result.stderr}`);
    }
  });
});

// ─── D1: Terminal state protection ───
// Requirement: 废弃状态转换禁止
// Scenario: abandoned 后拒绝所有 transition
describe('Terminal state protection — abandoned', () => {
  let dir;
  before(() => { dir = makeChangeDir(); });
  after(() => { cleanup(dir); });

  const allTargets = ['exploring', 'specifying', 'bridging', 'approved-for-build', 'executing', 'debugging', 'closing'];

  for (const target of allTargets) {
    it(`SHALL reject abandoned → ${target}`, () => {
      const result = runGuard('abandoned', target, dir);
      assert.equal(result.ok, false, `Abandoned → ${target} must be rejected (terminal state)`);
    });
  }
});

// Scenario: 从 closing 不能进入 abandoned
describe('Terminal state protection — closing', () => {
  let dir;
  before(() => { dir = makeChangeDir(); });
  after(() => { cleanup(dir); });

  it('SHALL reject closing → abandoned', () => {
    const result = runGuard('closing', 'abandoned', dir);
    assert.equal(result.ok, false, 'Closing → abandoned must be rejected (both terminal)');
  });
});

// ─── D1: Fast-path validation ───
// Requirement: Guard 检查矩阵完整性
// Scenario: fast-path 有降级保护
describe('Fast-path validation', () => {
  let dir;
  before(() => { dir = makeChangeDir(); });
  after(() => { cleanup(dir); });

  it('SHALL support hotfix fast-path (exploring → bridging)', () => {
    const result = runGuard('exploring', 'bridging', dir, 'hotfix');
    // May fail on schema-valid or other checks, but should NOT be "unknown transition"
    if (!result.ok) {
      assert.ok(!result.stderr?.includes('unknown'), `Hotfix fast-path should be defined: ${result.stderr}`);
    }
  });

  it('SHALL support tweak fast-path (exploring → approved-for-build)', () => {
    const result = runGuard('exploring', 'approved-for-build', dir, 'tweak');
    if (!result.ok) {
      assert.ok(!result.stderr?.includes('unknown'), `Tweak fast-path should be defined: ${result.stderr}`);
    }
  });
});

describe('Independent review transition gates', () => {
  for (const workflow of ['hotfix', 'tweak']) {
    it(`keeps ${workflow} specifying -> bridging independent of Planning review identities`, () => {
      const fixture = makeReviewFixture();
      try {
        writeState(fixture.changeDir, baseReviewState('specifying', { workflow }));

        const result = runGuardJson(
          'specifying',
          'bridging',
          fixture.changeDir,
          workflow,
        );

        assert.equal(result.pass, true, JSON.stringify(result));
        assert.equal(
          result.checks.find(check => check.dimension === 'review-approved')?.skipped,
          true,
          JSON.stringify(result),
        );
      } finally {
        cleanup(fixture.repo);
      }
    });
  }

  it('wires current Design/Tasks approval into specifying -> bridging', () => {
    const fixture = makeReviewFixture();
    try {
      let result = runGuardJson('specifying', 'bridging', fixture.changeDir);
      let review = result.checks.find(check => check.dimension === 'review-approved');
      assert.equal(review?.pass, false, JSON.stringify(result));

      const proposal = writeApprovedReview(fixture, 'proposal-specs');
      const state = baseReviewState('specifying', {
        dp_1_result: 'confirmed: product direction',
        dp_1_candidate_identity: proposal.identity,
      });
      writeState(fixture.changeDir, state);
      const design = writeApprovedReview(fixture, 'design-tasks');
      writeState(fixture.changeDir, {
        ...state,
        dp_2_result: 'confirmed: implementation direction',
        dp_2_candidate_identity: design.identity,
      });

      result = runGuardJson('specifying', 'bridging', fixture.changeDir);
      review = result.checks.find(check => check.dimension === 'review-approved');
      assert.equal(review?.pass, true, JSON.stringify(result));
    } finally {
      cleanup(fixture.repo);
    }
  });

  it('wires current Final approval into executing -> closing and detects Git drift', () => {
    const fixture = makeReviewFixture();
    try {
      const proposal = writeApprovedReview(fixture, 'proposal-specs');
      let state = baseReviewState('executing', {
        execution_base_commit: fixture.base,
        dp_1_result: 'confirmed: product direction',
        dp_1_candidate_identity: proposal.identity,
      });
      writeState(fixture.changeDir, state);
      const design = writeApprovedReview(fixture, 'design-tasks');
      state = {
        ...state,
        dp_2_result: 'confirmed: implementation direction',
        dp_2_candidate_identity: design.identity,
      };
      writeState(fixture.changeDir, state);
      writeApprovedReview(fixture, 'final');

      let result = runGuardJson('executing', 'closing', fixture.changeDir);
      let review = result.checks.find(check => check.dimension === 'review-approved');
      assert.equal(review?.pass, true, JSON.stringify(result));

      writeFileSync(join(fixture.repo, 'src', 'feature.mjs'), 'export const value = 2;\n');
      result = runGuardJson('executing', 'closing', fixture.changeDir);
      review = result.checks.find(check => check.dimension === 'review-approved');
      assert.equal(review?.pass, false, JSON.stringify(result));
    } finally {
      cleanup(fixture.repo);
    }
  });

  it('binds DP-2 to the current Design review for exact full workflow', () => {
    const fixture = makeReviewFixture();
    try {
      const proposal = writeApprovedReview(fixture, 'proposal-specs');
      let state = baseReviewState('specifying', {
        dp_1_result: 'confirmed: product direction',
        dp_1_candidate_identity: proposal.identity,
      });
      writeState(fixture.changeDir, state);
      const design = writeApprovedReview(fixture, 'design-tasks');

      state = {
        ...state,
        dp_2_result: 'confirmed: implementation direction',
        dp_2_candidate_identity: `sha256:${'0'.repeat(64)}`,
      };
      writeState(fixture.changeDir, state);
      assert.equal(checkReviewApproved(
        fixture.changeDir,
        'specifying',
        'bridging',
      ).pass, false);

      writeState(fixture.changeDir, {
        ...state,
        dp_2_candidate_identity: design.identity,
      });
      assert.equal(checkReviewApproved(
        fixture.changeDir,
        'specifying',
        'bridging',
      ).pass, true);

    } finally {
      cleanup(fixture.repo);
    }
  });

  it('allows a legacy approved contract to resume without a new DP-3 field', () => {
    const fixture = makeReviewFixture();
    try {
      writeState(fixture.changeDir, baseReviewState('bridging', {
        dp_3_result: 'approved: contract',
        contract_hash: computeContractHash(fixture.changeDir),
      }));

      assert.deepEqual(
        checkDpGate(fixture.changeDir, 'bridging', 'approved-for-build'),
        { pass: true, failures: [] },
      );
    } finally {
      cleanup(fixture.repo);
    }
  });
});

function makeReviewFixture() {
  const repo = mkdtempSync(join(tmpdir(), 'ssf-review-guard-'));
  runGit(repo, ['init', '-q', '-b', 'main']);
  runGit(repo, ['config', 'user.email', 'tests@example.com']);
  runGit(repo, ['config', 'user.name', 'Spec Superflow Tests']);
  mkdirSync(join(repo, 'src'), { recursive: true });
  writeFileSync(join(repo, 'src', 'feature.mjs'), 'export const value = 1;\n');
  runGit(repo, ['add', '.']);
  runGit(repo, ['commit', '-qm', 'baseline']);
  const base = runGit(repo, ['rev-parse', 'HEAD']);
  const changeDir = join(repo, 'changes', 'example');
  mkdirSync(join(changeDir, 'specs', 'example'), { recursive: true });
  mkdirSync(join(changeDir, 'reviews'), { recursive: true });
  writeFileSync(join(changeDir, 'user-intent.md'), '# Intent\nIndependent review.\n');
  writeFileSync(join(changeDir, 'proposal.md'), '# Proposal\nThree stages.\n');
  writeFileSync(join(changeDir, 'specs', 'example', 'spec.md'), '# Spec\nBehavior.\n');
  writeFileSync(join(changeDir, 'design.md'), '# Design\nOne Reviewer.\n');
  writeFileSync(join(changeDir, 'tasks.md'), '# Tasks\n\n## Batch 1\n- [x] Done.\n');
  writeFileSync(join(changeDir, 'execution-contract.md'), '# Contract\nApproved.\n');
  writeFileSync(join(changeDir, 'pr-summary.md'), '# PR Summary\nTests pass.\n');
  writeFileSync(join(changeDir, 'known-risks.md'), '# Risks\nRuntime pending.\n');
  writeFileSync(join(changeDir, 'runtime-evidence.md'), '# Evidence\nPENDING.\n');
  writeState(changeDir, baseReviewState('specifying'));
  return { repo, changeDir, base };
}

function baseReviewState(state, overrides = {}) {
  return {
    state,
    workflow: 'full',
    change_name: 'example',
    batches_completed: 1,
    test_result: 'pass',
    ...overrides,
  };
}

function writeApprovedReview(fixture, stage) {
  const state = readState(fixture.changeDir);
  const candidate = computeReviewCandidate({
    changeDir: fixture.changeDir,
    stage,
    ...(stage === 'design-tasks' ? {
      prerequisiteIdentities: {
        'proposal-specs': state.dp_1_candidate_identity,
      },
    } : {}),
    ...(stage === 'final' ? {
      repoRoot: fixture.repo,
      base: fixture.base,
      prerequisiteIdentities: {
        'proposal-specs': state.dp_1_candidate_identity,
        'design-tasks': state.dp_2_candidate_identity,
      },
    } : {}),
  });
  const report = {
    stage,
    candidate_identity: candidate.identity,
    verdict: 'Approved',
    findings: [],
    questions: [],
    review_focus: ['correctness'],
    summary: 'Approved.',
    residual_risks: ['Runtime pending.'],
    ...(stage === 'final' ? { review_base: candidate.review_base } : {}),
  };
  writeFileSync(
    join(fixture.changeDir, 'reviews', `${stage}-current.json`),
    `${JSON.stringify(report)}\n`,
  );
  return candidate;
}

function runGuardJson(from, to, changeDir, workflow = 'full') {
  const result = spawnSync(process.execPath, [
    GUARD, 'check', changeDir, from, to, '--json', '--workflow', workflow,
  ], {
    cwd: ROOT,
    encoding: 'utf8',
  });
  assert.ok(result.stdout, result.stderr);
  return JSON.parse(result.stdout);
}

function runGit(cwd, args) {
  const result = spawnSync('git', ['-C', cwd, ...args], { encoding: 'utf8' });
  assert.equal(result.status, 0, result.stderr);
  return result.stdout.trim();
}
