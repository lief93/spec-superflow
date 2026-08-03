// tests/lib/guard.test.mjs
// Tests for scripts/guard/guard.mjs — transition matrix and workflow mode skipping
import { describe, it, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, mkdirSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { execSync } from 'node:child_process';

let tempDir;
const GUARD_PATH = join(process.cwd(), 'scripts/guard/guard.mjs');

describe('guard: transition matrix', () => {
  before(() => {
    tempDir = mkdtempSync(join(tmpdir(), 'ssf-guard-test-'));
    // Create minimal artifacts so artifact checks can pass
    writeFileSync(join(tempDir, 'proposal.md'), '## Why\nThis is a test proposal for guard testing purposes. The system needs to support feature X which will enable users to accomplish their goals more efficiently.\n## What Changes\n- Add feature X');
    mkdirSync(join(tempDir, 'specs'), { recursive: true });
    writeFileSync(join(tempDir, 'specs', 'spec.md'), '## ADDED Requirements\n### Requirement: Feature X\nThe system SHALL do X.\n#### Scenario: basic\n- **WHEN** user triggers\n- **THEN** system responds');
    writeFileSync(join(tempDir, 'design.md'), '## Context\nTest design\n## Decisions\n### Decision 1\n- Choice: A\n- Rationale: B');
    writeFileSync(join(tempDir, 'tasks.md'), '## File Structure\n- Create: src/x.ts\n## Tasks\n### 1.1 Task\n- [x] done');
  });

  after(() => {
    if (tempDir) rmSync(tempDir, { recursive: true, force: true });
  });

  function runGuard(fromState, toState, opts = '') {
    try {
      const result = execSync(
        `node ${GUARD_PATH} check ${tempDir} ${fromState} ${toState} --json ${opts}`,
        { encoding: 'utf-8', stdio: ['pipe', 'pipe', 'pipe'] }
      );
      return { exitCode: 0, output: JSON.parse(result.trim()) };
    } catch (err) {
      if (err.stdout) {
        try { return { exitCode: err.status, output: JSON.parse(err.stdout.trim()) }; }
        catch { return { exitCode: err.status, output: err.stderr || err.message }; }
      }
      return { exitCode: err.status || 1, output: err.stderr || err.message };
    }
  }

  it('exploring→specifying starts artifact generation without requiring artifacts', () => {
    const result = runGuard('exploring', 'specifying');
    assert.equal(result.exitCode, 0, `Expected exit 0 but got ${result.exitCode}: ${JSON.stringify(result.output)}`);
    assert.deepEqual(result.output.checks, []);
  });

  it('specifying→bridging runs artifacts, schema, current review, and DP binding checks', () => {
    const result = runGuard('specifying', 'bridging');
    assert.equal(result.exitCode, 1, `Expected missing review/DP bindings to block: ${JSON.stringify(result.output)}`);
    const dims = result.output.checks.map(c => c.dimension);
    assert.ok(dims.includes('artifacts-exist'));
    assert.ok(dims.includes('schema-valid'));
    assert.ok(dims.includes('review-approved'));
    assert.ok(dims.includes('dp-gate-passed'));
    assert.equal(result.output.checks.find(c => c.dimension === 'artifacts-exist').pass, true);
    assert.equal(result.output.checks.find(c => c.dimension === 'schema-valid').pass, true);
    assert.equal(result.output.checks.find(c => c.dimension === 'review-approved').pass, false);
    assert.equal(result.output.checks.find(c => c.dimension === 'dp-gate-passed').pass, true);
  });

  it('bridging→approved-for-build requires artifacts-exist + schema-valid + contract-fresh', () => {
    const result = runGuard('bridging', 'approved-for-build');
    // contract-fresh may fail since no contract exists, but the check should run
    const dims = result.output.checks.map(c => c.dimension);
    assert.ok(dims.includes('artifacts-exist'));
    assert.ok(dims.includes('schema-valid'));
    assert.ok(dims.includes('contract-fresh'));
  });

  it('approved-for-build→executing requires artifacts-exist + contract-fresh', () => {
    const result = runGuard('approved-for-build', 'executing');
    const dims = result.output.checks.map(c => c.dimension);
    assert.ok(dims.includes('artifacts-exist'));
    assert.ok(dims.includes('contract-fresh'));
  });

  it('executing→closing requires tasks-complete + tests-passing', () => {
    const result = runGuard('executing', 'closing');
    const dims = result.output.checks.map(c => c.dimension);
    assert.ok(dims.includes('tasks-complete'));
    assert.ok(dims.includes('tests-passing'));
  });

  it('executing→debugging requires no checks', () => {
    const result = runGuard('executing', 'debugging');
    assert.equal(result.exitCode, 0);
    assert.deepStrictEqual(result.output.checks, []);
  });

  it('exploring→approved-for-build requires artifacts-exist', () => {
    const result = runGuard('exploring', 'approved-for-build');
    assert.equal(result.exitCode, 0, `Expected exit 0 but got ${result.exitCode}: ${JSON.stringify(result.output)}`);
    const dims = result.output.checks.map(c => c.dimension);
    assert.ok(dims.includes('artifacts-exist'));
  });

  it('unknown transition returns error', () => {
    const result = runGuard('closing', 'exploring');
    assert.equal(result.exitCode, 1);
  });
});

describe('guard: workflow mode skipping', () => {
  before(() => {
    tempDir = mkdtempSync(join(tmpdir(), 'ssf-guard-mode-'));
    writeFileSync(join(tempDir, 'proposal.md'), '## Why\nTest for mode skipping\n## What Changes\n- Add Y');
  });

  after(() => {
    if (tempDir) rmSync(tempDir, { recursive: true, force: true });
  });

  function runGuardWithMode(fromState, toState, workflow) {
    try {
      const result = execSync(
        `node ${GUARD_PATH} check ${tempDir} ${fromState} ${toState} --json --workflow ${workflow}`,
        { encoding: 'utf-8', stdio: ['pipe', 'pipe', 'pipe'] }
      );
      return { exitCode: 0, output: JSON.parse(result.trim()) };
    } catch (err) {
      if (err.stdout) {
        try { return { exitCode: err.status, output: JSON.parse(err.stdout.trim()) }; }
        catch { return { exitCode: err.status, output: err.stderr || err.message }; }
      }
      return { exitCode: err.status || 1, output: err.stderr || err.message };
    }
  }

  it('tweak mode skips schema-valid, contract-fresh, and artifacts-exist', () => {
    // specifying→bridging normally requires artifacts-exist + schema-valid
    const result = runGuardWithMode('specifying', 'bridging', 'tweak');
    const checks = result.output.checks;
    for (const c of checks) {
      if (['schema-valid', 'contract-fresh', 'artifacts-exist'].includes(c.dimension)) {
        assert.equal(c.pass, true, `${c.dimension} should be skipped in tweak mode`);
        assert.equal(c.skipped, true, `${c.dimension} should be marked skipped in tweak mode`);
      }
    }
  });

  it('hotfix mode skips schema-valid only', () => {
    const result = runGuardWithMode('specifying', 'bridging', 'hotfix');
    const checks = result.output.checks;
    const schemaCheck = checks.find(c => c.dimension === 'schema-valid');
    assert.equal(schemaCheck.pass, true);
    assert.equal(schemaCheck.skipped, true);
    // artifacts-exist should NOT be skipped in hotfix
    const artifactsCheck = checks.find(c => c.dimension === 'artifacts-exist');
    assert.ok(artifactsCheck, 'artifacts-exist should still run in hotfix mode');
    assert.notEqual(artifactsCheck.skipped, true);
  });

  it('full mode does not skip any checks', () => {
    const result = runGuardWithMode('specifying', 'bridging', 'full');
    const checks = result.output.checks;
    for (const c of checks) {
      assert.notEqual(c.skipped, true, `${c.dimension} should not be skipped in full mode`);
    }
  });

  it('invalid workflow mode exits with error', () => {
    const result = runGuardWithMode('exploring', 'specifying', 'invalid-mode');
    assert.equal(result.exitCode, 2);
  });
});

describe('guard: artifact timing', () => {
  before(() => {
    tempDir = mkdtempSync(join(tmpdir(), 'ssf-guard-artifacts-'));
  });

  after(() => {
    if (tempDir) rmSync(tempDir, { recursive: true, force: true });
  });

  function runGuard(fromState, toState) {
    try {
      const result = execSync(
        `node ${GUARD_PATH} check ${tempDir} ${fromState} ${toState} --json`,
        { encoding: 'utf-8', stdio: ['pipe', 'pipe', 'pipe'] }
      );
      return { exitCode: 0, output: JSON.parse(result.trim()) };
    } catch (err) {
      if (err.stdout) {
        try { return { exitCode: err.status, output: JSON.parse(err.stdout.trim()) }; }
        catch { return { exitCode: err.status, output: err.stderr || err.message }; }
      }
      return { exitCode: err.status || 1, output: err.stderr || err.message };
    }
  }

  it('allows entering specifying before the first planning artifact exists', () => {
    const result = runGuard('exploring', 'specifying');
    assert.equal(result.exitCode, 0);
    assert.equal(result.output.pass, true);
    assert.deepEqual(result.output.checks, []);
  });
});

describe('guard: completed batch count', () => {
  let changeDir;

  before(() => {
    changeDir = mkdtempSync(join(tmpdir(), 'ssf-guard-batches-'));
  });

  after(() => {
    if (changeDir) rmSync(changeDir, { recursive: true, force: true });
  });

  function writeFixture(batchNumbers, batchesCompleted) {
    const batches = batchNumbers.map(number => `## Batch ${number}: Batch ${number}
- [x] Complete batch ${number}
`).join('\n');
    writeFileSync(join(changeDir, 'tasks.md'), `# Tasks\n\n${batches}`);
    writeFileSync(
      join(changeDir, '.spec-superflow.yaml'),
      `state: executing
workflow: full
batches_completed: ${batchesCompleted}
test_result: pass
`,
    );
  }

  function runClosingGuard() {
    try {
      const output = execSync(
        `node ${GUARD_PATH} check ${changeDir} executing closing --json --workflow tweak`,
        { encoding: 'utf-8', stdio: ['pipe', 'pipe', 'pipe'] },
      );
      return { exitCode: 0, output: JSON.parse(output.trim()) };
    } catch (error) {
      return {
        exitCode: error.status || 1,
        output: JSON.parse(error.stdout.toString().trim()),
      };
    }
  }

  it('rejects an under-reported completed batch count', () => {
    writeFixture([1, 2], 0);
    const result = runClosingGuard();

    assert.equal(result.exitCode, 1);
    assert.ok(
      result.output.checks.some(check =>
        check.dimension === 'tasks-complete'
        && check.failures.some(failure => failure.includes('batches_completed is 0') && failure.includes('2'))),
    );
  });

  it('rejects an over-reported completed batch count', () => {
    writeFixture([1, 2], 3);
    const result = runClosingGuard();

    assert.equal(result.exitCode, 1);
    assert.ok(
      result.output.checks.some(check =>
        check.dimension === 'tasks-complete'
        && check.failures.some(failure => failure.includes('batches_completed is 3') && failure.includes('2'))),
    );
  });

  it('rejects a gap in Batch numbering', () => {
    writeFixture([1, 3], 2);
    const result = runClosingGuard();

    assert.equal(result.exitCode, 1);
    assert.ok(
      result.output.checks.some(check =>
        check.dimension === 'tasks-complete'
        && check.failures.some(failure => failure.includes('Batch numbering'))),
    );
  });

  it('accepts sequential Batch headings with the matching completed count', () => {
    writeFixture([1, 2], 2);
    const result = runClosingGuard();

    assert.equal(result.exitCode, 0, JSON.stringify(result.output));
    assert.equal(result.output.pass, true);
  });
});
