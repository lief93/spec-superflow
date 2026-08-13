import assert from 'node:assert/strict';
import { execFileSync, spawnSync } from 'node:child_process';
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  rmSync,
  symlinkSync,
  writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, describe, it } from 'node:test';

const ROOT = process.cwd();
const CLI = join(ROOT, 'scripts', 'spec-superflow.mjs');
const fixtures = [];

afterEach(() => {
  while (fixtures.length) rmSync(fixtures.pop(), { recursive: true, force: true });
});

function run(args, cwd = ROOT, options = {}) {
  const result = spawnSync(process.execPath, [CLI, ...args], {
    cwd,
    encoding: 'utf8',
    timeout: options.timeout ?? 10_000,
  });
  return {
    exitCode: result.status ?? 1,
    stdout: result.stdout.trim(),
    stderr: result.stderr.trim(),
    signal: result.signal,
  };
}

function createPlanningFixture() {
  const project = mkdtempSync(join(tmpdir(), 'ssf-developer-override-'));
  fixtures.push(project);
  execFileSync('git', ['init', '-q', '-b', 'main'], { cwd: project });
  execFileSync('git', ['config', 'user.email', 'tests@example.com'], { cwd: project });
  execFileSync('git', ['config', 'user.name', 'Spec Superflow Tests'], { cwd: project });
  writeFileSync(join(project, 'README.md'), '# Baseline\n');
  execFileSync('git', ['add', 'README.md'], { cwd: project });
  execFileSync('git', ['commit', '-qm', 'baseline'], { cwd: project });

  const change = join(project, 'changes', 'minor-execution-amendment');
  mkdirSync(join(change, 'specs', 'empty-state'), { recursive: true });
  writeFileSync(join(change, 'user-intent.md'), '# Intent\nAdd an empty state.\n');
  writeFileSync(join(change, 'proposal.md'), `## Why
The existing screen needs an explicit empty state so users understand that no items are currently available.

## What Changes
- Render an empty state when no items are available.
`);
  writeFileSync(join(change, 'specs', 'empty-state', 'spec.md'), `## ADDED Requirements

### Requirement: Empty state
The screen SHALL show an empty state when no items are available.

#### Scenario: No items
- **WHEN** the item list is empty
- **THEN** the empty state is visible
`);
  writeFileSync(join(change, 'design.md'), `# Design

## Context
Reuse the existing empty-state component.

## Requirement And Scenario Coverage
| Requirement | Scenario | Decision | Affected Area | Baseline / Reuse | Constraint / Deviation | Ownership Reason |
|---|---|---|---|---|---|---|
| Empty state | No items | Reuse empty-state component | Screen content | Existing EmptyState | No deviation | Screen owns rendering |

## Decisions
### Decision: Reuse empty-state component
- **Choice**: Reuse the existing component.
- **Rationale**: Avoid duplicate UI behavior.
- **Alternatives considered**: Add a new component.

## Risks And Trade-Offs
- Existing semantics must remain queryable.
`);
  writeFileSync(join(change, 'tasks.md'), `# Tasks

## Batch 1: Empty state
### AC: Empty state / No items
- [ ] **Files**
  - \`Screen.kt\` — render the existing empty-state component.
- [ ] **TDD Test Plan**
  - **Unit** | Android | Add | \`ScreenTest.kt\` | \`shows empty state\` | Empty content renders the empty state.

### Batch Verification
- **RED / Baseline**: \`./gradlew test --tests ScreenTest\`
- **GREEN**: \`./gradlew test --tests ScreenTest\`
- **Regression**: \`./gradlew test\`
`);
  writeFileSync(join(change, 'execution-contract.md'), `# Execution Contract

## Approved Artifacts
- proposal.md
- specs/empty-state/spec.md
- design.md
- tasks.md

## Execution Mode
- Mode: Inline

## Batch Gates
| Batch | Entry Gate | Exit Gate | Review Gate |
|---|---|---|---|
| Batch 1 | Planning ready | Tests pass | Final review |

## Verification
- Run planned tests.

## Frontend Verification
- Frontend Impact: Yes

## Stop Conditions
- Stop when planning changes.
`);
  assert.equal(run(['state', 'init', change], project).exitCode, 0);
  return { project, change };
}

function writeRetryAmendment(change) {
  writeFileSync(join(change, 'user-intent.md'), `# Intent
While implementing the empty state, add a Retry button. Update the Plan and do not run planning review again.
`);
  writeFileSync(join(change, 'proposal.md'), `## Why
The empty state needs a direct recovery action when loading can be retried.

## What Changes
- Keep the existing empty-state message.
- Add a Retry button that requests the screen to load items again.
`);
  writeFileSync(join(change, 'specs', 'empty-state', 'spec.md'), `## ADDED Requirements

### Requirement: Recoverable empty state
The screen SHALL retain the empty-state message and offer Retry when loading can be retried.

#### Scenario: No items
- **WHEN** the item list is empty
- **THEN** the empty-state message remains visible

#### Scenario: Retry loading
- **WHEN** the user activates Retry from the empty state
- **THEN** the screen requests item loading again
`);
  writeFileSync(join(change, 'design.md'), `# Technical Design

## Context
- Current state: Screen owns empty-state rendering and its existing load callback.
- Constraints: Reuse the existing empty-state component and load callback.

## Requirement And Scenario Coverage
| Requirement | Scenario | Design Decision | Affected Area | Baseline / Reuse | Constraint / Deviation | Why Here |
|---|---|---|---|---|---|---|
| Recoverable empty state | No items | Reuse screen content seam | Screen content | Existing empty-state component | No deviation | Screen owns empty-state rendering |
| Recoverable empty state | Retry loading | Reuse screen content seam | Screen content | Existing load callback | No deviation | Screen owns the user action and callback |

## Decisions
### Decision: Reuse screen content seam
- **Choice**: Add Retry to the existing empty-state content and invoke the existing load callback.
- **Rationale**: The behavior stays at the current UI ownership boundary.
- **Alternatives considered**: Add a second recovery controller.

## Risks And Trade-Offs
- Duplicate taps could request loading twice -> Disable Retry while loading through existing state.
`);
  writeFileSync(join(change, 'tasks.md'), `# Implementation Tasks

## Batch 1: Add recoverable empty state

Depends on: None

### AC: No items
- **Requirement**: Recoverable empty state
- **User-visible**: Yes

#### File Changes
##### Modify \`app/src/main/java/example/Screen.kt\`
- **Why this file**: It owns the current empty-state rendering.
- **Change**: Preserve the existing empty-state message while adding the recovery action.
- **Reuse**: Existing empty-state component.

#### TDD Test Plan
| Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|
| UI | Android | Add | \`app/src/androidTest/java/example/ScreenTest.kt\` | \`empty state keeps its message\` | Empty content still renders the existing empty-state message. |

### AC: Retry loading
- **Requirement**: Recoverable empty state
- **User-visible**: Yes

#### File Changes
##### Modify \`app/src/main/java/example/Screen.kt\`
- **Why this file**: It owns the empty-state control and existing load callback.
- **Change**: Add Retry and invoke the existing load callback from the rendered control.
- **Reuse**: Existing load callback and loading state.

#### TDD Test Plan
| Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|
| UI | Android | Add | \`app/src/androidTest/java/example/ScreenRetryTest.kt\` | \`retry requests item loading\` | Activating the rendered Retry control invokes item loading once. |

### Batch Verification
- [ ] **RED / Baseline**: Run \`./gradlew connectedDebugAndroidTest\`; the retry case fails because the control is absent and the message case passes.
- [ ] **GREEN / Regression**: Run \`./gradlew connectedDebugAndroidTest test\`; both exact UI cases and affected regressions pass.
`);
}

function writeRetryContract(change) {
  writeFileSync(join(change, 'execution-contract.md'), `# Execution Contract

## Approved Artifacts
- **Planning Lock**: \`.spec-superflow.yaml > artifacts_hash\`

| Artifact | Source Of Truth |
|---|---|
| Proposal | \`proposal.md\` |
| Specs | \`specs/\` |
| Design | \`design.md\` |
| Tasks | \`tasks.md\` |

## Execution Mode
- **Mode**: Inline
- **Selection rationale**: One existing Android screen owns the local amendment.

## Batch Gates
| Batch | Entry Gate | Exit Gate | Review Gate |
|---|---|---|---|
| Batch 1 | Refreshed planning lock and contract approval | Planned UI tests and regression pass | Existing final review policy |

## Verification
| Check | Command Or Procedure | Evidence Required |
|---|---|---|
| AC tests | Run the exact Android UI cases in tasks.md | Per-case result in pr-summary.md |
| Regression | \`./gradlew connectedDebugAndroidTest test\` | Zero failures |

## Frontend Verification
- **Frontend Impact**: Yes
- **Reason**: The amendment adds a visible Android control and interaction.

| Check | Obligation | Scope | Target Environment | Command Or Procedure | Evidence Required |
|---|---|---|---|---|---|
| UI Test | Required by tasks.md | Both UI rows in tasks.md | Android instrumentation runtime | Run the exact planned test files and cases | Per-AC test result |
| Device Test | Required | Reachable empty-state Retry branch | Project-standard Android emulator | Open the empty state and activate Retry | Emulator, branch, and result |

## Stop Conditions
- Stop if the existing load callback cannot represent retry behavior.
- Stop if implementation requires a new architecture boundary.
`);
}

describe('developer override CLI', () => {
  it('records a content-bound review waiver that becomes stale after Planning changes', () => {
    const { project, change } = createPlanningFixture();
    const waived = run([
      'override', 'waive-review', change, 'proposal-specs',
      '--reason', 'Developer accepts this local addition without another planning review.',
      '--json',
    ], project);

    assert.equal(waived.exitCode, 0, waived.stderr);
    const result = JSON.parse(waived.stdout);
    assert.equal(result.action, 'waive-review');
    assert.equal(result.actor, 'developer');
    assert.match(result.candidate_identity, /^sha256:/);

    const current = run(['review', 'check', change, 'proposal-specs', '--json'], project);
    assert.equal(current.exitCode, 0, current.stderr);
    assert.equal(JSON.parse(current.stdout).code, 'developer-waived');

    writeFileSync(join(change, 'proposal.md'), `${readFileSync(join(change, 'proposal.md'), 'utf8')}\n- Add analytics.\n`);
    const stale = run(['review', 'check', change, 'proposal-specs', '--json'], project);
    assert.notEqual(stale.exitCode, 0);
    assert.equal(JSON.parse(stale.stdout).code, 'stale-waiver');
  });

  it('waives only semantic review and still fails malformed Planning validation', () => {
    const { project, change } = createPlanningFixture();
    const waived = run([
      'override', 'waive-review', change, 'proposal-specs',
      '--reason', 'Developer accepts the semantic review risk for this exact candidate.',
      '--json',
    ], project);
    assert.equal(waived.exitCode, 0, waived.stderr);
    assert.equal(
      JSON.parse(run(['review', 'check', change, 'proposal-specs', '--json'], project).stdout).code,
      'developer-waived',
    );

    writeFileSync(join(change, 'tasks.md'), '# Tasks\n\nThis is not the required Tasks structure.\n');

    const stillWaived = run(['review', 'check', change, 'proposal-specs', '--json'], project);
    assert.equal(stillWaived.exitCode, 0, stillWaived.stdout || stillWaived.stderr);
    assert.equal(JSON.parse(stillWaived.stdout).code, 'developer-waived');
    const validation = run(['validate', change], project);
    assert.notEqual(validation.exitCode, 0);
    assert.match(`${validation.stdout}\n${validation.stderr}`, /tasks\.md|Batch|TDD Test Plan/i);
  });

  it('records developer permission for another review without changing workflow state', () => {
    const { project, change } = createPlanningFixture();
    const before = run(['state', 'get', change, 'state'], project).stdout;
    const continued = run([
      'override', 'continue-review', change, 'design-tasks',
      '--reason', 'Developer wants the remaining findings fixed and reviewed again.',
      '--json',
    ], project);

    assert.equal(continued.exitCode, 0, continued.stderr);
    assert.equal(JSON.parse(continued.stdout).action, 'continue-review');
    assert.equal(run(['state', 'get', change, 'state'], project).stdout, before);
    assert.match(readFileSync(join(change, 'developer-overrides.jsonl'), 'utf8'), /continue-review/);
  });

  it('rewinds to a requested earlier state and invalidates downstream approvals', () => {
    const { project, change } = createPlanningFixture();
    const statePath = join(change, '.spec-superflow.yaml');
    writeFileSync(
      statePath,
      readFileSync(statePath, 'utf8')
        .replace('state: exploring', 'state: executing')
        .replace('dp_3_result: null', 'dp_3_result: approved: old contract')
        .replace('dp_4_result: null', 'dp_4_result: approved: old execution'),
    );
    mkdirSync(join(change, 'reviews'), { recursive: true });
    writeFileSync(join(change, 'reviews', 'final-current.json'), '{}\n');

    const rewound = run([
      'override', 'rewind', change, 'specifying',
      '--reason', 'Developer chose a full replan after the scope expanded.',
      '--json',
    ], project);

    assert.equal(rewound.exitCode, 0, rewound.stderr);
    assert.equal(run(['state', 'get', change, 'state'], project).stdout, 'specifying');
    assert.equal(existsSync(join(change, 'reviews', 'final-current.json')), false);
    assert.equal(run(['state', 'get', change, 'dp_3_result'], project).stdout, 'null');
    assert.match(readFileSync(join(change, 'developer-overrides.jsonl'), 'utf8'), /full replan/);
  });

  it('starts a light replan in executing without rewinding and invalidates the old contract approval', () => {
    const { project, change } = createPlanningFixture();
    const statePath = join(change, '.spec-superflow.yaml');
    writeFileSync(
      statePath,
      readFileSync(statePath, 'utf8')
        .replace('state: exploring', 'state: executing')
        .replace('workflow: auto', 'workflow: full')
        .replace('dp_1_result: null', 'dp_1_result: confirmed: old behavior')
        .replace('dp_1_candidate_identity: null', `dp_1_candidate_identity: sha256:${'1'.repeat(64)}`)
        .replace('dp_2_result: null', 'dp_2_result: confirmed: old implementation')
        .replace('dp_2_candidate_identity: null', `dp_2_candidate_identity: sha256:${'2'.repeat(64)}`)
        .replace('dp_3_result: null', 'dp_3_result: approved: old contract')
        .replace('dp_4_result: null', 'dp_4_result: inline execution'),
    );
    mkdirSync(join(change, 'reviews'), { recursive: true });
    writeFileSync(join(change, 'reviews', 'final-current.json'), '{}\n');

    const result = run([
      'override', 'light-replan', change,
      '--reason', 'Developer added one local behavior during implementation.',
      '--json',
    ], project);

    assert.equal(result.exitCode, 0, result.stderr);
    assert.equal(run(['state', 'get', change, 'state'], project).stdout, 'executing');
    assert.equal(run(['state', 'get', change, 'dp_1_result'], project).stdout, 'null');
    assert.equal(run(['state', 'get', change, 'dp_2_result'], project).stdout, 'null');
    assert.equal(run(['state', 'get', change, 'dp_3_result'], project).stdout, 'null');
    assert.equal(run(['state', 'get', change, 'dp_4_result'], project).stdout, 'null');
    assert.equal(existsSync(join(change, 'reviews', 'final-current.json')), false);
    assert.match(readFileSync(join(change, 'developer-overrides.jsonl'), 'utf8'), /light-replan/);

    const blocked = run(['override', 'resume-check', change, '--json'], project);
    assert.notEqual(blocked.exitCode, 0);
    assert.match(JSON.parse(blocked.stdout).failures.join('\n'), /Planning lock|Contract lock|DP-3|DP-4/);

    assert.equal(run(['state', 'init', change], project).exitCode, 0);
    assert.equal(run([
      'state', 'set', change, 'dp_3_result', 'approved: refreshed contract',
    ], project).exitCode, 0);
    assert.equal(run([
      'state', 'set', change, 'dp_4_result', 'inline: continue current execution',
    ], project).exitCode, 0);
    const ready = run(['override', 'resume-check', change, '--json'], project);
    assert.notEqual(ready.exitCode, 0);
    assert.match(JSON.parse(ready.stdout).failures.join('\n'), /Proposal\/Specs review|Design\/Tasks review/);
  });

  it('completes an executing Story amendment through Planning waivers and a refreshed contract', () => {
    const { project, change } = createPlanningFixture();
    const statePath = join(change, '.spec-superflow.yaml');
    writeFileSync(
      statePath,
      readFileSync(statePath, 'utf8')
        .replace('state: exploring', 'state: executing')
        .replace('workflow: auto', 'workflow: full')
        .replace('dp_3_result: null', 'dp_3_result: approved: original contract')
        .replace('dp_4_result: null', 'dp_4_result: inline: original execution'),
    );

    const light = run([
      'override', 'light-replan', change,
      '--reason', 'Add Retry, update the Plan, and do not run planning review again.', '--json',
    ], project);
    assert.equal(light.exitCode, 0, light.stderr);
    writeRetryAmendment(change);

    const proposal = run([
      'override', 'waive-review', change, 'proposal-specs',
      '--reason', 'Developer explicitly approved the amended behavior without another review.',
      '--json',
    ], project);
    assert.equal(proposal.exitCode, 0, proposal.stderr);
    const proposalIdentity = JSON.parse(proposal.stdout).candidate_identity;
    assert.equal(run([
      'state', 'set', change, 'dp_1_result', 'confirmed: add Retry and preserve the empty-state message',
    ], project).exitCode, 0);
    assert.equal(run([
      'state', 'set', change, 'dp_1_candidate_identity', proposalIdentity,
    ], project).exitCode, 0);

    const design = run([
      'override', 'waive-review', change, 'design-tasks',
      '--reason', 'Developer explicitly approved reuse of the existing screen and load callback.',
      '--json',
    ], project);
    assert.equal(design.exitCode, 0, design.stderr);
    const designIdentity = JSON.parse(design.stdout).candidate_identity;
    assert.equal(run([
      'state', 'set', change, 'dp_2_result', 'confirmed: reuse existing screen and load callback',
    ], project).exitCode, 0);
    assert.equal(run([
      'state', 'set', change, 'dp_2_candidate_identity', designIdentity,
    ], project).exitCode, 0);

    writeRetryContract(change);
    assert.equal(run(['state', 'init', change], project).exitCode, 0);
    const validation = run(['validate', change], project);
    assert.equal(validation.exitCode, 0, validation.stdout || validation.stderr);
    assert.equal(run([
      'state', 'set', change, 'dp_3_result', 'approved: refreshed Retry execution contract',
    ], project).exitCode, 0);
    assert.equal(run([
      'state', 'set', change, 'dp_4_result', 'inline: continue the current implementation',
    ], project).exitCode, 0);

    const resume = run(['override', 'resume-check', change, '--json'], project);
    assert.equal(resume.exitCode, 0, resume.stdout || resume.stderr);
    assert.equal(JSON.parse(resume.stdout).ready, true);
    assert.equal(run(['state', 'get', change, 'state'], project).stdout, 'executing');
    assert.equal(
      JSON.parse(run(['review', 'check', change, 'proposal-specs', '--json'], project).stdout).code,
      'developer-waived',
    );
    assert.equal(
      JSON.parse(run(['review', 'check', change, 'design-tasks', '--json'], project).stdout).code,
      'developer-waived',
    );
    const actions = readFileSync(join(change, 'developer-overrides.jsonl'), 'utf8');
    assert.match(actions, /light-replan/);
    assert.equal((actions.match(/waive-review/g) ?? []).length, 2);
  });

  it('does not invent fixed Reviewer gates for a non-full light replan', () => {
    const { project, change } = createPlanningFixture();
    const statePath = join(change, '.spec-superflow.yaml');
    writeFileSync(
      statePath,
      readFileSync(statePath, 'utf8')
        .replace('state: exploring', 'state: executing')
        .replace('workflow: auto', 'workflow: hotfix'),
    );
    assert.equal(run([
      'override', 'light-replan', change,
      '--reason', 'Refresh this non-full plan before continuing.',
    ], project).exitCode, 0);
    assert.equal(run(['state', 'init', change], project).exitCode, 0);
    assert.equal(run([
      'state', 'set', change, 'dp_3_result', 'approved: refreshed hotfix contract',
    ], project).exitCode, 0);
    assert.equal(run([
      'state', 'set', change, 'dp_4_result', 'inline: continue hotfix execution',
    ], project).exitCode, 0);

    const resume = run(['override', 'resume-check', change, '--json'], project);
    assert.equal(resume.exitCode, 0, resume.stdout || resume.stderr);
    assert.equal(JSON.parse(resume.stdout).ready, true);
  });

  it('abandons a non-terminal change only on an explicit developer decision', () => {
    const { project, change } = createPlanningFixture();
    const abandoned = run([
      'override', 'abandon', change,
      '--reason', 'Developer decided the requirement is no longer valuable.',
      '--json',
    ], project);

    assert.equal(abandoned.exitCode, 0, abandoned.stderr);
    assert.equal(run(['state', 'get', change, 'state'], project).stdout, 'abandoned');
    assert.match(readFileSync(join(change, 'abandonment-summary.md'), 'utf8'), /Developer decided/);

    const repeated = run([
      'override', 'abandon', change,
      '--reason', 'Try again.',
      '--json',
    ], project);
    assert.notEqual(repeated.exitCode, 0);
  });

  it('rejects missing reasons and unsupported review stages', () => {
    const { project, change } = createPlanningFixture();
    assert.notEqual(run(['override', 'abandon', change], project).exitCode, 0);
    assert.notEqual(run([
      'override', 'waive-review', change, 'unknown', '--reason', 'No review.',
    ], project).exitCode, 0);
  });

  it('fails quickly when a final waiver Change is outside a Git repository', () => {
    const { project, change } = createPlanningFixture();
    const base = execFileSync('git', ['rev-parse', 'HEAD'], {
      cwd: project,
      encoding: 'utf8',
    }).trim();
    const proposal = run([
      'override', 'waive-review', change, 'proposal-specs',
      '--reason', 'Developer accepts the current product direction.', '--json',
    ], project);
    assert.equal(proposal.exitCode, 0, proposal.stderr);
    assert.equal(run([
      'state', 'set', change, 'dp_1_result', 'confirmed: current product direction',
    ], project).exitCode, 0);
    assert.equal(run([
      'state', 'set', change, 'dp_1_candidate_identity',
      JSON.parse(proposal.stdout).candidate_identity,
    ], project).exitCode, 0);
    const design = run([
      'override', 'waive-review', change, 'design-tasks',
      '--reason', 'Developer accepts the current implementation direction.', '--json',
    ], project);
    assert.equal(design.exitCode, 0, design.stderr);
    assert.equal(run([
      'state', 'set', change, 'dp_2_result', 'confirmed: current implementation direction',
    ], project).exitCode, 0);
    assert.equal(run([
      'state', 'set', change, 'dp_2_candidate_identity',
      JSON.parse(design.stdout).candidate_identity,
    ], project).exitCode, 0);
    const statePath = join(change, '.spec-superflow.yaml');
    writeFileSync(
      statePath,
      readFileSync(statePath, 'utf8').replace(
        'execution_base_commit: null',
        `execution_base_commit: ${base}`,
      ),
    );
    rmSync(join(project, '.git'), { recursive: true, force: true });

    const result = run([
      'override', 'waive-review', change, 'final',
      '--reason', 'Developer accepts the current implementation without final review.',
    ], project, { timeout: 1_000 });

    assert.notEqual(result.exitCode, 0);
    assert.notEqual(result.signal, 'SIGTERM', 'repository lookup must not hang');
    assert.match(result.stderr, /Git repository/i);
  });

  it('fails closed when reviews is a symlink during a light replan', () => {
    const { project, change } = createPlanningFixture();
    const statePath = join(change, '.spec-superflow.yaml');
    writeFileSync(
      statePath,
      readFileSync(statePath, 'utf8').replace('state: exploring', 'state: executing'),
    );
    const outside = join(project, 'outside-reviews');
    mkdirSync(outside);
    const reviews = join(change, 'reviews');
    symlinkSync(outside, reviews);

    const result = run([
      'override', 'light-replan', change,
      '--reason', 'Developer requested a local planning amendment.',
    ], project);

    assert.notEqual(result.exitCode, 0);
    assert.equal(run(['state', 'get', change, 'state'], project).stdout, 'executing');
    assert.deepEqual(readdirSync(outside), []);
  });
});
