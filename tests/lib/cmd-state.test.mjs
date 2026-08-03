// tests/lib/cmd-state.test.mjs
// Tests for scripts/lib/cmd-state.mjs
import { describe, it, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, readFileSync, mkdirSync, rmSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { execSync } from 'node:child_process';

const CLI_PATH = join(process.cwd(), 'scripts/spec-superflow.mjs');
let tempDir;

function ssf(args, options = {}) {
  try {
    const result = execSync(
      `node ${CLI_PATH} ${args}`,
      { encoding: 'utf-8', stdio: ['pipe', 'pipe', 'pipe'], cwd: options.cwd || process.cwd() }
    );
    return { exitCode: 0, stdout: result.trim(), stderr: '' };
  } catch (err) {
    return { exitCode: err.status || 1, stdout: err.stdout?.trim() || '', stderr: err.stderr?.trim() || err.message };
  }
}

describe('cmd-state: init', () => {
  before(() => {
    tempDir = mkdtempSync(join(tmpdir(), 'ssf-state-cmd-'));
    // Create minimal artifacts for hash computation
    writeFileSync(join(tempDir, 'proposal.md'), '## Why\nTest proposal for state command testing, needs to be long enough for validation rules\n## What Changes\n- Add feature X');
  });

  after(() => {
    if (tempDir) rmSync(tempDir, { recursive: true, force: true });
  });

  it('creates .spec-superflow.yaml with hashes', () => {
    const result = ssf(`state init ${tempDir}`);
    assert.equal(result.exitCode, 0, `Expected exit 0 but got ${result.exitCode}: ${result.stderr}`);

    const stateFile = join(tempDir, '.spec-superflow.yaml');
    assert.ok(existsSync(stateFile));
  });

  it('reports artifacts_hash in init output', () => {
    const result = ssf(`state init ${tempDir}`);
    assert.ok(result.stdout.includes('artifacts_hash'));
  });

  it('--json flag outputs JSON with ok: true', () => {
    const result = ssf(`state init ${tempDir} --json`);
    const parsed = JSON.parse(result.stdout);
    assert.equal(parsed.ok, true);
    assert.ok(parsed.artifacts_hash.startsWith('sha256:'));
  });
});

describe('cmd-state: check', () => {
  before(() => {
    tempDir = mkdtempSync(join(tmpdir(), 'ssf-state-check-'));
    writeFileSync(join(tempDir, 'proposal.md'), '## Why\nTest proposal for state checking with enough chars to pass validation rules.\n## What Changes\n- Feature X');
  });

  after(() => {
    if (tempDir) rmSync(tempDir, { recursive: true, force: true });
  });

  it('reports consistent after init', () => {
    ssf(`state init ${tempDir}`);
    const result = ssf(`state check ${tempDir}`);
    assert.equal(result.exitCode, 0);
    assert.ok(result.stdout.includes('consistent'));
  });

  it('reports inconsistent after artifact change', () => {
    ssf(`state init ${tempDir}`);
    // Modify an artifact
    writeFileSync(join(tempDir, 'proposal.md'), '## Why\nModified proposal with different content for inconsistency testing.\n## What Changes\n- Modified feature');
    const result = ssf(`state check ${tempDir}`);
    assert.equal(result.exitCode, 1);
    assert.ok(result.stdout.includes('INCONSISTENT'));
  });

  it('--json outputs structured data', () => {
    ssf(`state init ${tempDir}`);
    const result = ssf(`state check ${tempDir} --json`);
    const parsed = JSON.parse(result.stdout);
    assert.equal(parsed.consistent, true);
    assert.ok(parsed.stored_hash);
    assert.ok(parsed.current_hash);
    assert.equal(parsed.state, 'exploring');
  });

  it('remains consistent when only task completion checkboxes change', () => {
    const changeDir = mkdtempSync(join(tmpdir(), 'ssf-state-task-progress-'));

    try {
      writeFileSync(join(changeDir, 'proposal.md'), '## Why\nTask progress must not invalidate approved planning content.\n## What Changes\n- Track task completion independently.');
      writeFileSync(join(changeDir, 'tasks.md'), '# Tasks\n- [ ] Implement approved behavior');
      assert.equal(ssf(`state init ${changeDir}`).exitCode, 0);

      writeFileSync(join(changeDir, 'tasks.md'), '# Tasks\n- [x] Implement approved behavior');
      const result = ssf(`state check ${changeDir} --json`);
      const parsed = JSON.parse(result.stdout);

      assert.equal(result.exitCode, 0, result.stderr);
      assert.equal(parsed.consistent, true);
      assert.equal(parsed.stored_hash, parsed.current_hash);
    } finally {
      rmSync(changeDir, { recursive: true, force: true });
    }
  });
});

describe('cmd-state: transition', () => {
  before(() => {
    tempDir = mkdtempSync(join(tmpdir(), 'ssf-state-trans-'));
    writeFileSync(join(tempDir, 'proposal.md'), '## Why\nTest proposal for state transition validation, meeting the minimum length requirement.\n## What Changes\n- Add feature');
    writeFileSync(join(tempDir, 'design.md'), '# Design\n## Context\nTest.\n## Goals\nTest.\n## Decisions\n### D1\n- Choice: Test\n- Rationale: Test\n\n## Risks And Trade-Offs\nNone.');
    writeFileSync(join(tempDir, 'tasks.md'), '# Tasks\n- [x] Task 1');
    mkdirSync(join(tempDir, 'specs'));
    writeFileSync(join(tempDir, 'specs', 'test.md'), '## ADDED Requirements\n### Requirement: Test\nSHALL work.\n#### Scenario: Test\n- **WHEN** test\n- **THEN** test');
  });

  after(() => {
    if (tempDir) rmSync(tempDir, { recursive: true, force: true });
  });

  it('transitions from exploring to specifying', () => {
    ssf(`state init ${tempDir}`);
    const result = ssf(`state transition ${tempDir} specifying`);
    assert.equal(result.exitCode, 0);
    assert.ok(result.stdout.includes('exploring -> specifying'));
  });

  it('--json outputs from/to', () => {
    // Re-init to ensure we start from exploring
    rmSync(join(tempDir, '.spec-superflow.yaml'), { force: true });
    ssf(`state init ${tempDir}`);
    // exploring→specifying is the next legal mainline transition
    const result = ssf(`state transition ${tempDir} specifying --json`);
    const parsed = JSON.parse(result.stdout);
    assert.equal(parsed.ok, true);
    assert.equal(parsed.from, 'exploring');
    assert.equal(parsed.to, 'specifying');
  });

  it('persists state across invocations', () => {
    ssf(`state init ${tempDir}`);
    // Legal transition: exploring → specifying
    ssf(`state transition ${tempDir} specifying`);

    // Check state persisted
    const result = ssf(`state check ${tempDir} --json`);
    const parsed = JSON.parse(result.stdout);
    assert.equal(parsed.state, 'specifying');
  });

  it('accepts relative change directories when running guard checks', () => {
    const projectDir = mkdtempSync(join(tmpdir(), 'ssf-state-relative-root-'));
    const relChangeDir = join('changes', 'relative-transition');
    const changeDir = join(projectDir, relChangeDir);

    try {
      mkdirSync(join(changeDir, 'specs'), { recursive: true });
      writeFileSync(join(changeDir, 'proposal.md'), '## Why\nRelative path transition should resolve against the caller working directory before invoking guard checks.\n## What Changes\n- Exercise relative change paths.');
      writeFileSync(join(changeDir, 'design.md'), '# Design\n## Context\nRelative path guard check.\n## Goals\nResolve paths before guard execution.');
      writeFileSync(join(changeDir, 'tasks.md'), '# Tasks\n- [x] Prepare relative path fixture');
      writeFileSync(join(changeDir, 'specs', 'test.md'), '## ADDED Requirements\n### Requirement: Relative state transition\nThe system SHALL resolve relative change directories before guard checks.\n#### Scenario: Relative path\n- **WHEN** transition receives a relative path\n- **THEN** guard checks read the caller project artifacts');

      const init = ssf(`state init ${relChangeDir}`, { cwd: projectDir });
      assert.equal(init.exitCode, 0, init.stderr);

      const transition = ssf(`state transition ${relChangeDir} specifying`, { cwd: projectDir });
      assert.equal(transition.exitCode, 0, transition.stderr);
      assert.ok(transition.stdout.includes('exploring -> specifying'));
    } finally {
      rmSync(projectDir, { recursive: true, force: true });
    }
  });

  it('progresses a new full-workflow Change through every mainline state', () => {
    const projectDir = mkdtempSync(join(tmpdir(), 'ssf-state-lifecycle-'));
    const changeDir = join(projectDir, 'changes', 'full-lifecycle');

    function expectState(expected) {
      const result = ssf(`state get ${changeDir} state`);
      assert.equal(result.exitCode, 0, result.stderr);
      assert.equal(result.stdout, expected);
    }

    try {
      assert.equal(ssf(`state init ${changeDir}`).exitCode, 0);
      expectState('exploring');

      assert.equal(ssf(`state transition ${changeDir} specifying`).exitCode, 0);
      expectState('specifying');

      mkdirSync(join(changeDir, 'specs', 'lifecycle'), { recursive: true });
      writeFileSync(join(changeDir, 'proposal.md'), `## Why
The workflow must persist every mainline state so later guards inspect the real lifecycle instead of inferred intent.
## What Changes
- Exercise the full state-machine lifecycle.
`);
      writeFileSync(join(changeDir, 'specs', 'lifecycle', 'spec.md'), `## ADDED Requirements
### Requirement: Persist workflow state
The system SHALL persist each approved mainline transition.
#### Scenario: Complete the workflow
- **WHEN** every phase gate passes
- **THEN** the Change reaches closing
`);
      writeFileSync(join(changeDir, 'design.md'), `# Design
## Context
The CLI owns persisted workflow state.
## Goals
Persist each legal mainline transition.
## Requirement And Scenario Coverage
| Requirement | Scenario | Design Decision | Affected Area | Why Here |
|---|---|---|---|---|
| Persist workflow state | Complete the workflow | Use state transition commands | State CLI | The CLI owns persisted state |
## Decisions
### Decision: Use state transition commands
- Choice: Run the guarded CLI transition for every phase.
- Rationale: The state file remains the auditable source of lifecycle state.
- Alternatives: Infer state only from artifacts.
## Risks And Trade-Offs
- Every phase must run its transition command.
`);
      writeFileSync(join(changeDir, 'tasks.md'), `# Tasks
## Interfaces
- Batch 1 verifies the state-machine lifecycle.
## Batch 1: Complete the workflow
Depends on: None
### AC: Complete the workflow
- **Requirement**: Persist workflow state
- **User-visible**: No
#### File Changes
##### Modify \`skills/workflow-start/SKILL.md\`
- **Responsibility**: Persist every successful mainline route.
- **Change**: Pair every guard with its state transition.
- **Used by**: Workflow routing.
#### TDD Test Plan
| Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|
| Integration | Node | Add | \`tests/lib/cmd-state.test.mjs\` | \`progresses a new full-workflow Change through every mainline state\` | Every mainline state is persisted in order. |
#### TDD Steps
- [ ] RED: Prove a missing transition leaves stale state.
- [ ] GREEN: Persist every successful transition.
- [ ] REFACTOR: Run state and guard regression tests.
`);

      assert.equal(ssf(`state transition ${changeDir} bridging`).exitCode, 0);
      expectState('bridging');

      writeFileSync(join(changeDir, 'execution-contract.md'), `# Execution Contract
## Intent Lock
Persist every mainline workflow transition.
## Approved Behavior
The Change reaches each state only after its guard passes.
## Requirement Traceability
| Requirement | Approved Behavior | Test Obligation | Batch |
|---|---|---|---|
| Persist workflow state | Persist every successful mainline transition | Execute the lifecycle integration test | Batch 1 |
## AC Test Matrix
| Requirement | AC | Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|---|---|
| Persist workflow state | Complete the workflow | Integration | Node | Add | \`tests/lib/cmd-state.test.mjs\` | \`progresses a new full-workflow Change through every mainline state\` | Every mainline state is persisted in order. |
## Design Constraints
Use the guarded state CLI.
## Task Batches
### Batch 1
- Complete the lifecycle integration.
## Test Obligations
- Run the lifecycle integration test.
## Frontend Verification
- **Frontend Impact**: No
- **Reason**: State-machine behavior has no user interface.
## Execution Mode
- Mode: Inline
## Verification Dimensions
| Dimension | Status | Findings |
|---|---|---|
| Completeness | Pending | - |
## Review Gates
- Review before closure.
## Escalation Rules
- Stop on any failed transition.
`);
      assert.equal(ssf(`state init ${changeDir}`).exitCode, 0);
      assert.equal(ssf(`state set ${changeDir} dp_3_result "approved: lifecycle contract"`).exitCode, 0);
      assert.equal(ssf(`state transition ${changeDir} approved-for-build`).exitCode, 0);
      expectState('approved-for-build');

      assert.equal(ssf(`state set ${changeDir} dp_4_result "inline execution"`).exitCode, 0);
      assert.equal(ssf(`state transition ${changeDir} executing`).exitCode, 0);
      expectState('executing');

      const tasksPath = join(changeDir, 'tasks.md');
      writeFileSync(
        tasksPath,
        readFileSync(tasksPath, 'utf-8').replaceAll('- [ ]', '- [x]'),
      );
      writeFileSync(join(changeDir, 'pr-summary.md'), `## AC Test Evidence
| Requirement | AC | Layer | Platform | Test File | Test Case | Result | Command | Evidence |
|---|---|---|---|---|---|---|---|---|
| Persist workflow state | Complete the workflow | Integration | Node | \`tests/lib/cmd-state.test.mjs\` | \`progresses a new full-workflow Change through every mainline state\` | Pass | \`node --test tests/lib/cmd-state.test.mjs\` | Mainline states persisted in order. |
`);
      assert.equal(ssf(`state set ${changeDir} batches_completed 1`).exitCode, 0);
      assert.equal(ssf(`state set ${changeDir} test_result pass`).exitCode, 0);
      assert.equal(ssf(`state rebuild ${changeDir}`).exitCode, 0);

      const closingOwners = [
        ['release-archivist', readFileSync(join(process.cwd(), 'skills/release-archivist/SKILL.md'), 'utf-8')],
        ['workflow-start', readFileSync(join(process.cwd(), 'skills/workflow-start/SKILL.md'), 'utf-8')],
      ].filter(([, content]) =>
        content.includes('ssf state transition <change-dir> closing')
        || content.includes('ssf state transition <dir> closing'));

      for (const [owner] of closingOwners) {
        const transition = ssf(`state transition ${changeDir} closing`);
        assert.equal(
          transition.exitCode,
          0,
          `${owner} attempted a duplicate closing transition: ${transition.stderr}`,
        );
      }
      assert.equal(closingOwners.length, 1, 'exactly one Skill must own executing -> closing');
      expectState('closing');
    } finally {
      rmSync(projectDir, { recursive: true, force: true });
    }
  });
});

describe('cmd-state: get', () => {
  before(() => {
    tempDir = mkdtempSync(join(tmpdir(), 'ssf-state-get-'));
    writeFileSync(join(tempDir, 'proposal.md'), '## Why\nTest proposal for get command, needs to be long enough.\n## What Changes\n- Feature');
  });

  after(() => {
    if (tempDir) rmSync(tempDir, { recursive: true, force: true });
  });

  it('gets a field value', () => {
    ssf(`state init ${tempDir}`);
    const result = ssf(`state get ${tempDir} state`);
    assert.equal(result.exitCode, 0);
    assert.equal(result.stdout.trim(), 'exploring');
  });

  it('returns null for unset fields', () => {
    ssf(`state init ${tempDir}`);
    const result = ssf(`state get ${tempDir} dp_5_result`);
    assert.ok(result.stdout.includes('null'));
  });

  it('--json returns structured output', () => {
    ssf(`state init ${tempDir}`);
    const result = ssf(`state get ${tempDir} state --json`);
    const parsed = JSON.parse(result.stdout);
    assert.equal(parsed.field, 'state');
    assert.equal(parsed.value, 'exploring');
  });

  it('errors without field argument', () => {
    const result = ssf(`state get ${tempDir}`);
    assert.equal(result.exitCode, 2);
  });
});

describe('cmd-state: set', () => {
  before(() => {
    tempDir = mkdtempSync(join(tmpdir(), 'ssf-state-set-'));
    writeFileSync(join(tempDir, 'proposal.md'), '## Why\nTest proposal for the set subcommand validation.\n## What Changes\n- Test feature');
  });

  after(() => {
    if (tempDir) rmSync(tempDir, { recursive: true, force: true });
  });

  it('sets a settable field', () => {
    ssf(`state init ${tempDir}`);
    const result = ssf(`state set ${tempDir} workflow hotfix`);
    assert.equal(result.exitCode, 0);
    assert.ok(result.stdout.includes('hotfix'));
  });

  it('sets a DP field', () => {
    ssf(`state init ${tempDir}`);
    ssf(`state set ${tempDir} dp_1_result "confirmed: csv export"`);
    const get = ssf(`state get ${tempDir} dp_1_result`);
    assert.ok(get.stdout.includes('confirmed: csv export'));
  });

  it('persists dp_0_result when set through the CLI', () => {
    ssf(`state init ${tempDir}`);
    ssf(`state set ${tempDir} dp_0_result "confirmed: scope locked"`);
    const get = ssf(`state get ${tempDir} dp_0_result`);
    assert.ok(get.stdout.includes('confirmed: scope locked'));
  });

  it('rejects non-settable fields', () => {
    ssf(`state init ${tempDir}`);
    const result = ssf(`state set ${tempDir} state executing`);
    assert.equal(result.exitCode, 1);
    // Error goes to stderr for console.error
    assert.ok(result.stderr.includes('not settable') || result.stdout.includes('not settable'),
      `Expected 'not settable' in output but got stdout: "${result.stdout}" stderr: "${result.stderr}"`);
  });

  it('rejects unknown fields', () => {
    ssf(`state init ${tempDir}`);
    const result = ssf(`state set ${tempDir} nonexistent_field value`);
    assert.equal(result.exitCode, 1);
  });

  it('--json outputs structured result', () => {
    ssf(`state init ${tempDir}`);
    const result = ssf(`state set ${tempDir} test_result pass --json`);
    const parsed = JSON.parse(result.stdout);
    assert.equal(parsed.ok, true);
    assert.equal(parsed.field, 'test_result');
    assert.equal(parsed.value, 'pass');
  });
});

describe('cmd-state: rebuild', () => {
  before(() => {
    tempDir = mkdtempSync(join(tmpdir(), 'ssf-state-rebuild-'));
    writeFileSync(join(tempDir, 'proposal.md'), '## Why\nRebuild test proposal with sufficient content length.\n## What Changes\n- Rebuild feature');
  });

  after(() => {
    if (tempDir) rmSync(tempDir, { recursive: true, force: true });
  });

  it('rebuilds state from artifacts', () => {
    ssf(`state init ${tempDir}`);
    const result = ssf(`state rebuild ${tempDir}`);
    assert.equal(result.exitCode, 0);
    assert.ok(result.stdout.includes('rebuilt'));
  });

  it('--json returns ok with state', () => {
    ssf(`state init ${tempDir}`);
    const result = ssf(`state rebuild ${tempDir} --json`);
    const parsed = JSON.parse(result.stdout);
    assert.equal(parsed.ok, true);
    assert.equal(parsed.state, 'exploring');
  });
});

describe('cmd-state: error handling', () => {
  it('errors when no change-dir provided', () => {
    const result = ssf('state init');
    assert.equal(result.exitCode, 2);
  });

  it('errors on unknown subcommand', () => {
    const result = ssf('state invalid-subcommand /tmp');
    assert.equal(result.exitCode, 2);
  });
});
