import assert from 'node:assert/strict';
import { execFileSync, spawnSync } from 'node:child_process';
import { copyFileSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { basename, join } from 'node:path';
import { describe, it } from 'node:test';

const ROOT = process.cwd();

describe('packaged CLI runtime', () => {
  it('installs from the packed artifact and validates a tracked change', () => {
    const temp = mkdtempSync(join(tmpdir(), 'ssf-packaged-cli-'));
    const packOutput = JSON.parse(execFileSync(
      'npm',
      ['pack', '--json', '--pack-destination', temp],
      { cwd: ROOT, encoding: 'utf8' },
    ));
    const archive = join(temp, basename(packOutput[0].filename));
    const prefix = join(temp, 'prefix');

    execFileSync(
      'npm',
      ['install', '--global', '--prefix', prefix, archive],
      { cwd: ROOT, stdio: 'pipe' },
    );

    const cli = join(prefix, 'bin', 'ssf');
    const version = JSON.parse(readFileSync(join(ROOT, 'package.json'), 'utf8')).version;
    assert.equal(execFileSync(cli, ['--version'], { encoding: 'utf8' }).trim(), version);

    const project = join(temp, 'project');
    const change = join(project, 'changes', 'packaged-cli-check');
    mkdirSync(join(change, 'specs', 'packaged-cli'), { recursive: true });
    copyFileSync(join(ROOT, '.gitignore'), join(project, '.gitignore'));
    writeFileSync(join(change, 'proposal.md'), `# Change Proposal
## Why
The packaged CLI must validate change-local planning artifacts without relying on source-checkout-only files or historical Changes.
## What Changes
- Add an isolated validation fixture.
`);
    writeFileSync(join(change, 'specs', 'packaged-cli', 'spec.md'), `# Packaged CLI
## ADDED Requirements
### Requirement: Packaged CLI validates change artifacts
The installed CLI SHALL validate a complete change in another repository.
#### Scenario: Installed CLI validates a tracked change
- **WHEN** the installed CLI validates the isolated Change
- **THEN** validation succeeds
`);
    writeFileSync(join(change, 'design.md'), `# Technical Design
## Context
The fixture exercises the installed CLI outside its source checkout.
## Goals
- Prove packaged validation.
## Requirement And Scenario Coverage
| Requirement | Scenario | Design Decision | Affected Area | Why Here |
|---|---|---|---|---|
| Packaged CLI validates change artifacts | Installed CLI validates a tracked change | Use an isolated tracked fixture | Packaged CLI process | The fixture separates package runtime from source checkout state |
## Decisions
### Decision: Use an isolated tracked fixture
- **Choice**: Create and track a complete Change in a temporary Git repository.
- **Rationale**: It avoids coupling package verification to historical product Changes.
- **Alternatives considered**: Reuse a repository Change, which makes the runtime test depend on unrelated lifecycle artifacts.
## Risks And Trade-Offs
- Fixture drift -> validate it with the same installed CLI.
`);
    writeFileSync(join(change, 'tasks.md'), `# Implementation Tasks
## Interfaces
- One validation batch; no cross-batch interface.
## Batch 1: Validate the packaged CLI
Depends on: None
### AC: Installed CLI validates a tracked change
- **Requirement**: Packaged CLI validates change artifacts
- **User-visible**: No
#### File Changes
##### Create \`test/packaged-cli.test.mjs\`
- **Responsibility**: Exercise the installed CLI against this tracked Change.
- **Add**: Add the package runtime assertion.
- **Used by**: Package verification.
#### TDD Test Plan
| Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|
| Integration | Node | Add | \`test/packaged-cli.test.mjs\` | \`validates tracked change\` | The installed CLI validates complete tracked artifacts outside its source checkout. |
#### TDD Steps
- [ ] Run the installed CLI against the isolated Change.
`);
    writeFileSync(join(change, 'execution-contract.md'), `# Execution Contract
## Intent Lock
Validate a tracked Change with the installed packaged CLI.
## Approved Behavior
The installed CLI validates complete planning artifacts outside its source checkout.
## Requirement Traceability
| Requirement | Approved Behavior | Test Obligation | Batch |
|---|---|---|---|
| Packaged CLI validates change artifacts | Validate a tracked isolated Change | Run the package runtime integration case | Batch 1 |
## AC Test Matrix
| Requirement | AC | Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|---|---|
| Packaged CLI validates change artifacts | Installed CLI validates a tracked change | Integration | Node | Add | \`test/packaged-cli.test.mjs\` | \`validates tracked change\` | The installed CLI validates complete tracked artifacts outside its source checkout. |
## Design Constraints
Use the packed CLI and an isolated Git repository.
## Task Batches
### Batch 1
- Validate the isolated tracked Change.
## Test Obligations
- Package runtime validation must pass.
## Frontend Verification
- **Frontend Impact**: No
- **Reason**: This is a CLI integration fixture.
## Execution Mode
- **Mode**: Inline
## Verification Dimensions
| Dimension | Status | Findings |
|---|---|---|
| Completeness | Pending | Runtime test supplies evidence. |
## Review Gates
- Review package output before release.
## Escalation Rules
- Rebuild the package if validation fails.
`);
    execFileSync('git', ['init', '--quiet'], { cwd: project });
    execFileSync('git', ['add', '.gitignore', 'changes/packaged-cli-check'], { cwd: project });
    assert.match(
      execFileSync(
        'git',
        ['ls-files', '--error-unmatch', 'changes/packaged-cli-check/specs/packaged-cli/spec.md'],
        { cwd: project, encoding: 'utf8' },
      ),
      /spec\.md/,
    );

    const validation = spawnSync(
      cli,
      ['validate', 'changes/packaged-cli-check'],
      { cwd: project, encoding: 'utf8' },
    );
    assert.equal(validation.status, 0, `${validation.stdout}\n${validation.stderr}`);
    assert.match(validation.stdout, /All artifacts validated/);
  });
});
