import assert from 'node:assert/strict';
import { execFileSync, spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import {
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { basename, dirname, join } from 'node:path';
import { describe, it } from 'node:test';

const ROOT = process.cwd();

function write(root, relativePath, content) {
  const path = join(root, relativePath);
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, content);
}

function run(cli, cwd, args) {
  return spawnSync(cli, args, { cwd, encoding: 'utf8' });
}

function createValidChange(project) {
  const relative = 'changes/packed-review';
  write(project, `${relative}/user-intent.md`, '# Intent\nUse fixed independent review.\n');
  write(project, `${relative}/proposal.md`, `# Proposal

## Why

The installed CLI must validate and review a tracked Change without source-checkout-only files.

## What Changes

- Add one packed Review CLI acceptance fixture.

## Scope

### In Scope

- Candidate, record, check, and validation.

### Out of Scope

- Real host model execution.

## Impact

- Installed CLI runtime only.

## Capabilities

- packed-review
`);
  write(project, `${relative}/specs/packed-review/spec.md`, `## ADDED Requirements

### Requirement: Packed CLI reviews a tracked Change

The installed CLI SHALL validate and review the current tracked Change.

#### Scenario: Installed CLI records current Proposal approval

- **WHEN** the installed CLI receives a valid fixed Reviewer report
- **THEN** candidate, record, and check succeed for the current Proposal
`);
  write(project, `${relative}/design.md`, `# Design

## Context

The fixture runs outside the source checkout.

## Goals

- Prove installed Review CLI behavior.

## Project Baseline Alignment

- Reuse the installed public CLI only.

## Requirement And Scenario Coverage
| Requirement | Scenario | Design Decision | Affected Area | Baseline / Reuse | Constraint / Deviation | Why Here |
|---|---|---|---|---|---|---|
| Packed CLI reviews a tracked Change | Installed CLI records current Proposal approval | Use a tracked temporary Change | Installed CLI | Installed public CLI | No source-checkout dependency | The temporary repository separates package runtime from source state. |

## Decisions

### Decision: Use a tracked temporary Change

- **Choice**: Create and Git-track one complete Change in a temporary repository.
- **Rationale**: It exercises the installed package independently.
- **Alternatives considered**: Reusing a source Change would couple the test to delivery artifacts.

## Risks And Trade-Offs

- Fixture drift is caught by installed validation.
`);
  write(project, `${relative}/tasks.md`, `# Tasks

## Interfaces

- One batch with no external interface.

## Batch 1: Verify installed review

Depends on: None

### AC: Installed CLI records current Proposal approval

- **Requirement**: Packed CLI reviews a tracked Change
- **User-visible**: No

#### File Changes

##### Create \`tests/packed-review.test.mjs\`

- **Change**: Exercise candidate, record, and check through the installed CLI.

#### TDD Test Plan

| Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|
| Integration | Node.js 22 | Add | tests/packed-review.test.mjs | installed CLI records current Proposal approval | The installed package validates and checks a current fixed Reviewer result. |

#### TDD Steps

- [x] RED: Observe the installed Review command missing.
- [x] GREEN: Run candidate, record, and check successfully.
- [x] REFACTOR: Run installed validation and state check.
`);
  write(project, `${relative}/execution-contract.md`, `# Execution Contract

## Intent Lock

- **Change name**: packed-review
- **Problem to solve**: Prove installed Review CLI behavior.
- **In scope**: Candidate, record, check, validation.
- **Out of scope**: Real host model execution.

## Approved Behavior

- **Approved requirement summary**: Installed CLI validates and reviews the tracked Change.
- **Key scenarios**: Current Proposal approval.
- **Acceptance checks**: Installed candidate, record, check, validate, and state check.

## Requirement Traceability

| Requirement | Approved Behavior | Test Obligation | Batch |
|---|---|---|---|
| Packed CLI reviews a tracked Change | Valid fixed Proposal approval becomes current. | Installed CLI candidate, record, and check succeed. | Batch 1 |

## AC Test Matrix

| Requirement | AC | Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|---|---|
| Packed CLI reviews a tracked Change | Installed CLI records current Proposal approval | Integration | Node.js 22 | Add | tests/packed-review.test.mjs | installed CLI records current Proposal approval | The installed package validates and checks a current fixed Reviewer result. |

## Design Constraints

- **Project baseline source**: Installed CLI.
- **Selected classic implementations**: Temporary tracked Change.
- **Approved deviations**: None.
- **Project Memory source**: Not configured.
- **Technology constraints**: Node.js built-ins only.
- **Architecture constraints**: Public CLI interface.
- **Data and interface constraints**: Fixed report path.
- **Dependency constraints**: No network.
- **Reuse targets and extension points**: Installed runtime.
- **Runtime and platform facts**: Temporary repository.

## Task Batches

### Batch 1

- **Goal**: Verify installed Review CLI.
- **Inputs**: Tracked Change.
- **Outputs**: Current Proposal approval.
- **Done when**: Installed checks pass.

## Test Obligations

- **Behavior that must start with a failing test**: Installed Review command.
- **Required edge cases**: Removed commands fail.
- **Regression-sensitive areas**: Validation and state hashes.

## Frontend Verification

- **Frontend Impact**: No
- **Reason**: CLI-only fixture.

## Execution Mode

- **Mode**: Inline
- **Selection rationale**: One CLI scenario.

## Verification Dimensions

| Dimension | Status | Findings |
|---|---|---|
| Completeness | Pending | - |
| Correctness | Pending | - |
| Coherence | Pending | - |

**Overall conclusion**: Pending

## Review Gates

- **Mandatory review points**: Proposal approval.
- **Blocking categories**: Invalid or stale result.

## Escalation Rules

- **When to return to \`specifying\`**: Planning changes.
- **When to return to \`bridging\`**: Contract changes.
- **When implementation must not continue**: Installed validation fails.
`);
  return relative;
}

describe('packaged CLI runtime', () => {
  it('packages only the simplified independent review runtime', () => {
    const packOutput = JSON.parse(execFileSync(
      'npm',
      ['pack', '--json', '--dry-run'],
      { cwd: ROOT, encoding: 'utf8' },
    ));
    const files = new Set(packOutput[0].files.map(file => file.path));

    for (const path of [
      'agents/spec-superflow.agent.md',
      'agents/spec-superflow-reviewer.agent.md',
      '.opencode/agents/spec-superflow.md',
      '.opencode/agents/spec-superflow-reviewer.md',
      '.opencode/plugins/spec-superflow.js',
      'commands/workflow-init.md',
      'scripts/lib/cmd-review.mjs',
      'scripts/lib/review-candidate.mjs',
      'scripts/lib/review-evidence.mjs',
      'scripts/lib/worktree-review-candidate.mjs',
      'scripts/guard/checks/review-approved.mjs',
      'servers/spec-superflow-mcp.mjs',
      'skills/grill-me/SKILL.md',
    ]) {
      assert.equal(files.has(path), true, `${path} must be packaged`);
    }

    assert.equal(files.has('agents/spec-superflow-dev.agent.md'), false);
    assert.equal(files.has('agents/spec-superflow-setup.agent.md'), false);
    assert.equal(files.has('.opencode/agents/spec-superflow-dev.md'), false);
    assert.equal(
      [...files].some(path => /^(changes|tests|validation|release-assets)\//.test(path)),
      false,
    );
    assert.equal(
      [...files].some(path => /(?:^|\/)(?:\.DS_Store|\._[^/]+|[^/]+~|\.#[^/]+|#.*#)$/.test(path)),
      false,
    );
    const releaseChecklist = readFileSync(join(ROOT, 'docs', 'release-checklist.md'), 'utf8');
    assert.match(releaseChecklist, /before publishing a new version of `spec-superflow`/i);
    assert.match(releaseChecklist, /no local-only junk files are included/i);
    assert.match(
      releaseChecklist,
      /Plugin release[\s\S]*tgz SHA-256[\s\S]*entry count[\s\S]*hygiene[\s\S]*offline local install/i,
    );
    assert.equal(JSON.parse(readFileSync(join(ROOT, 'package.json'), 'utf8')).dependencies, undefined);
  });

  it('installs the archive and runs only candidate, record, and check on a tracked valid Change', () => {
    const temp = mkdtempSync(join(tmpdir(), 'ssf-packed-review-'));
    try {
      const packOutput = JSON.parse(execFileSync(
        'npm',
        ['pack', '--json', '--pack-destination', temp],
        { cwd: ROOT, encoding: 'utf8' },
      ));
      const archive = join(temp, basename(packOutput[0].filename));
      const archiveSha256 = createHash('sha256')
        .update(readFileSync(archive))
        .digest('hex');
      assert.match(archiveSha256, /^[a-f0-9]{64}$/);
      assert.notEqual(archiveSha256, '0'.repeat(64));
      assert.equal(Number.isInteger(packOutput[0].entryCount), true);
      assert.equal(packOutput[0].entryCount > 0, true);
      assert.equal(packOutput[0].entryCount, packOutput[0].files.length);
      const prefix = join(temp, 'prefix');
      execFileSync('npm', [
        'install',
        '--global',
        '--offline',
        '--ignore-scripts',
        '--prefix',
        prefix,
        archive,
      ], {
        cwd: ROOT,
        env: {
          ...process.env,
          npm_config_fetch_retries: '0',
          npm_config_registry: 'http://127.0.0.1:9/',
        },
        stdio: 'pipe',
      });
      const cli = join(prefix, 'bin', 'ssf');
      const expectedVersion = JSON.parse(readFileSync(join(ROOT, 'package.json'), 'utf8')).version;
      assert.equal(run(cli, ROOT, ['--version']).stdout.trim(), expectedVersion);
      const installedReviewer = readFileSync(join(
        prefix,
        'lib',
        'node_modules',
        'spec-superflow',
        'agents',
        'spec-superflow-reviewer.agent.md',
      ), 'utf8');
      assert.match(
        installedReviewer,
        /initial review[\s\S]*complete the applicable ordered scan before choosing a\s+verdict/i,
      );
      assert.match(installedReviewer, /every blocking\s+Finding[\s\S]*same `findings` array/i);
      assert.doesNotMatch(
        installedReviewer,
        /candidate_graph|message_graph|handoff_attestation|repair[-_ ]delta/i,
      );

      const project = join(temp, 'project');
      mkdirSync(project, { recursive: true });
      execFileSync('git', ['init', '-q', '-b', 'main'], { cwd: project });
      execFileSync('git', ['config', 'user.email', 'tests@example.com'], { cwd: project });
      execFileSync('git', ['config', 'user.name', 'Spec Superflow Tests'], { cwd: project });
      write(project, 'README.md', '# Packed runtime project\n');
      const change = createValidChange(project);
      execFileSync('git', ['add', '.'], { cwd: project });
      execFileSync('git', ['commit', '-qm', 'tracked valid change'], { cwd: project });

      let result = run(cli, project, ['state', 'init', change]);
      assert.equal(result.status, 0, result.stderr || result.stdout);
      result = run(cli, project, ['validate', change]);
      assert.equal(result.status, 0, result.stderr || result.stdout);

      const tasksPath = join(project, change, 'tasks.md');
      const originalTasks = readFileSync(tasksPath, 'utf8');
      write(project, `${change}/tasks.md`, `${originalTasks}
## Batch 2: Duplicate installed review proof

Depends on: Batch 1

### AC: Installed CLI duplicates current Proposal approval

- **Requirement**: Packed CLI reviews a tracked Change
- **User-visible**: No

#### File Changes

##### Modify \`tests/packed-review.test.mjs\`

- **Change**: Duplicate the existing installed review proof.

#### TDD Test Plan

| Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|
| Integration | Node.js 22 | Add | ./tests//packed-review.test.mjs | installed CLI records current Proposal approval | The path alias attempts to reuse another AC's exact test case. |

#### TDD Steps

- [ ] RED: Run the installed validator.
`);
      result = run(cli, project, ['validate', change]);
      assert.equal(result.status, 1, result.stderr || result.stdout);
      assert.match(
        result.stdout,
        /Exact Test Case has multiple AC owners:[\s\S]*Installed CLI records current Proposal approval[\s\S]*Installed CLI duplicates current Proposal approval/i,
      );
      write(project, `${change}/tasks.md`, originalTasks);

      result = run(cli, project, ['review', 'candidate', change, 'proposal-specs', '--json']);
      assert.equal(result.status, 0, result.stderr || result.stdout);
      const candidate = JSON.parse(result.stdout);
      assert.equal(candidate.stage, 'proposal-specs');
      assert.equal(Object.hasOwn(candidate, 'candidate_graph'), false);

      write(project, `${change}/reviews/proposal-specs-pending-report.json`, `${JSON.stringify({
        stage: candidate.stage,
        candidate_identity: candidate.identity,
        verdict: 'Approved',
        findings: [],
        questions: [],
        review_focus: ['scope', 'behavior', 'evidence'],
        summary: 'The packed Proposal and Specs candidate is approved.',
        residual_risks: ['Real host model execution remains separate.'],
      })}\n`);
      result = run(cli, project, ['review', 'record', change, 'proposal-specs', '--json']);
      assert.equal(result.status, 0, result.stderr || result.stdout);
      result = run(cli, project, ['review', 'check', change, 'proposal-specs', '--json']);
      assert.equal(result.status, 0, result.stderr || result.stdout);
      assert.equal(JSON.parse(result.stdout).pass, true);

      for (const removed of [
        ['state', 'next', change, '--json'],
        ['state', 'confirm', change, 'proposal-specs', '--json'],
        ['review', 'begin', change, 'proposal-specs', '--json'],
      ]) {
        assert.equal(run(cli, project, removed).status, 2, removed.join(' '));
      }
      result = run(cli, project, ['state', 'check', change]);
      assert.equal(result.status, 0, result.stderr || result.stdout);
    } finally {
      rmSync(temp, { recursive: true, force: true });
    }
  });
});
