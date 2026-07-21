// tests/lib/cmd-validate.test.mjs
// Tests for scripts/lib/cmd-validate.mjs
import { describe, it, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, readFileSync, mkdirSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { execFileSync } from 'node:child_process';

const CLI_PATH = join(process.cwd(), 'scripts/spec-superflow.mjs');
let tempDir;

function writeValidPlanningArtifacts(changeDir) {
  mkdirSync(join(changeDir, 'specs', 'rate-limit'), { recursive: true });
  writeFileSync(join(changeDir, 'proposal.md'), '## Why\nRate limiting is needed to protect shared resources from abusive bursts while keeping normal user traffic reliable.\n## What Changes\n- Add request rate limiting.');
  writeFileSync(join(changeDir, 'design.md'), `# Design
## Context
Rate limiting runs before expensive handlers.
## Goals
Reject over-limit traffic consistently.
## Requirement And Scenario Coverage
| Requirement | Scenario | Design Decision | Affected Area | Why Here |
|---|---|---|---|---|
| Rate limit requests | Request exceeds limit | Shared middleware | HTTP middleware | Middleware runs before expensive handlers |
## Decisions
### Decision: Shared middleware
- Choice: Shared middleware
- Rationale: It keeps enforcement consistent across endpoints.
- Alternatives: Per-handler checks.
## Risks And Trade-Offs
- Shared state must remain bounded.
`);
  writeFileSync(join(changeDir, 'tasks.md'), `# Tasks
## Interfaces
- Batch 1 produces the rate-limit middleware.
## Batch 1: Add request rate limiting
Depends on: None
### AC: Request exceeds limit
- **Requirement**: Rate limit requests
#### File Changes
##### Create \`src/rate-limit.ts\`
- **Responsibility**: Enforce the shared request limit before handlers run.
- **Add**: Add the middleware entry point and bounded counter storage.
- **Used by**: HTTP route registration.
#### TDD Steps
- [ ] Write the failing over-limit request test.
- [ ] Run it and confirm the expected failure.
- [ ] Implement the middleware.
- [ ] Run focused tests and confirm they pass.
- [ ] Commit the batch.
`);
  writeFileSync(join(changeDir, 'specs', 'rate-limit', 'spec.md'), '## ADDED Requirements\n\n### Requirement: Rate limit requests\n\nThe system SHALL reject requests that exceed the configured rate limit.\n\n#### Scenario: Request exceeds limit\n- **WHEN** a client sends too many requests\n- **THEN** the system returns a rate limit response\n');
}

function writeValidExecutionContract(changeDir) {
  writeFileSync(join(changeDir, 'execution-contract.md'), '# Execution Contract\n\n## Intent Lock\n\nAdd request rate limiting.\n\n## Approved Behavior\n\nRate limit requests when clients exceed configured limits.\n\n## Requirement Traceability\n\n| Requirement | Approved Behavior | Test Obligation | Batch |\n|---|---|---|---|\n| Rate limit requests | Reject over-limit requests before expensive handlers run | Focused tests for HTTP 429 and service-call prevention | Batch 1 |\n\n## Design Constraints\n\nUse shared middleware.\n\n## Task Batches\n\n### Batch 1\n\n- Add tests and middleware.\n\n## Test Obligations\n\n- Start with failing tests for Rate limit requests.\n\n## Execution Mode\n\n- Mode: Inline\n\n## Verification Dimensions\n\n| Dimension | Status | Findings |\n|---|---|---|\n| Completeness | Pending | - |\n\n## Review Gates\n\n- Review before closure.\n\n## Escalation Rules\n\n- Return to bridging if middleware shape changes.\n');
}

function runValidate(changeDir) {
  try {
    const stdout = execFileSync(process.execPath, [CLI_PATH, 'validate', changeDir], {
      encoding: 'utf-8',
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    return { exitCode: 0, stdout, stderr: '' };
  } catch (err) {
    return {
      exitCode: err.status || 1,
      stdout: err.stdout?.toString() || '',
      stderr: err.stderr?.toString() || err.message,
    };
  }
}

describe('cmd-validate', () => {
  before(() => {
    tempDir = mkdtempSync(join(tmpdir(), 'ssf-validate-'));
  });

  after(() => {
    if (tempDir) rmSync(tempDir, { recursive: true, force: true });
  });

  it('prints specs and execution-contract validation when artifacts are valid', () => {
    const changeDir = join(tempDir, 'valid-change');
    mkdirSync(changeDir, { recursive: true });
    writeValidPlanningArtifacts(changeDir);
    writeValidExecutionContract(changeDir);

    const result = runValidate(changeDir);

    assert.equal(result.exitCode, 0, result.stderr);
    assert.ok(result.stdout.includes('specs/rate-limit/spec.md'));
    assert.ok(result.stdout.includes('execution-contract.md'));
    assert.ok(result.stdout.includes('All artifacts validated'));
  });

  it('accepts an optional Decision prefix in design coverage', () => {
    const changeDir = join(tempDir, 'decision-prefix');
    mkdirSync(changeDir, { recursive: true });
    writeValidPlanningArtifacts(changeDir);
    writeValidExecutionContract(changeDir);
    const designPath = join(changeDir, 'design.md');
    const design = readFileSync(designPath, 'utf-8');
    writeFileSync(designPath, design.replace('| Shared middleware | HTTP middleware |', '| Decision: Shared middleware | HTTP middleware |'));

    const result = runValidate(changeDir);

    assert.equal(result.exitCode, 0, result.stderr);
    assert.ok(result.stdout.includes('All artifacts validated'));
  });

  it('fails when a spec scenario is missing from design coverage', () => {
    const changeDir = join(tempDir, 'design-missing-scenario');
    mkdirSync(changeDir, { recursive: true });
    writeValidPlanningArtifacts(changeDir);
    writeValidExecutionContract(changeDir);
    writeFileSync(join(changeDir, 'design.md'), `# Design
## Context
Rate limiting runs before handlers.
## Requirement And Scenario Coverage
| Requirement | Scenario | Design Decision | Affected Area | Why Here |
|---|---|---|---|---|
| Rate limit requests | Normal request | Shared middleware | HTTP middleware | Middleware owns request admission |
## Decisions
### Decision: Shared middleware
- Choice: Shared middleware
- Rationale: Shared enforcement.
`);

    const result = runValidate(changeDir);

    assert.equal(result.exitCode, 1);
    assert.ok(result.stdout.includes('Scenario missing from design coverage: Rate limit requests / Request exceeds limit'));
  });

  it('fails when a task batch does not explain its file changes', () => {
    const changeDir = join(tempDir, 'tasks-missing-file-changes');
    mkdirSync(changeDir, { recursive: true });
    writeValidPlanningArtifacts(changeDir);
    writeValidExecutionContract(changeDir);
    writeFileSync(join(changeDir, 'tasks.md'), `# Tasks
## Batch 1: Add request rate limiting
### AC: Request exceeds limit
- **Requirement**: Rate limit requests
#### TDD Steps
- [ ] Add tests and implementation.
`);

    const result = runValidate(changeDir);

    assert.equal(result.exitCode, 1);
    assert.ok(result.stdout.includes('Batch 1 AC "Request exceeds limit" is missing #### File Changes'));
  });

  it('allows a configured fast path to omit design while retaining AC-owned tasks', () => {
    const changeDir = join(tempDir, 'tasks-without-design-change');
    mkdirSync(changeDir, { recursive: true });
    writeValidPlanningArtifacts(changeDir);
    writeValidExecutionContract(changeDir);
    rmSync(join(changeDir, 'design.md'));
    writeFileSync(join(changeDir, 'tasks.md'), `# Tasks
## Batch 1: Adjust request limit copy
### AC: Request exceeds limit
- **Requirement**: Rate limit requests
#### File Changes
##### Modify \`src/rate-limit.ts\`
- **Change**: Adjust the existing response text without changing middleware behavior.
#### TDD Steps
- [ ] Update the focused assertion and implementation text.
`);

    const result = runValidate(changeDir);

    assert.equal(result.exitCode, 0, result.stderr);
    assert.ok(result.stdout.includes('All artifacts validated'));
  });

  it('fails when the same Scenario is assigned to more than one Batch AC section', () => {
    const changeDir = join(tempDir, 'duplicate-task-ac');
    mkdirSync(changeDir, { recursive: true });
    writeValidPlanningArtifacts(changeDir);
    writeValidExecutionContract(changeDir);
    writeFileSync(join(changeDir, 'tasks.md'), `# Tasks
## Batch 1: Add request rate limiting
### AC: Request exceeds limit
- **Requirement**: Rate limit requests
#### File Changes
##### Create \`src/rate-limit.ts\`
- **Add**: Add the shared middleware.
#### TDD Steps
- [ ] Add focused tests and implementation.
## Batch 2: Repeat request rate limiting
### AC: Request exceeds limit
- **Requirement**: Rate limit requests
#### File Changes
##### Modify \`src/rate-limit.ts\`
- **Change**: Repeat the same behavior in another batch.
#### TDD Steps
- [ ] Repeat the focused verification.
`);

    const result = runValidate(changeDir);

    assert.equal(result.exitCode, 1);
    assert.ok(result.stdout.includes('Scenario assigned to multiple Batch AC sections: Rate limit requests / Request exceeds limit'));
  });

  it('rejects context.md beside a capability spec.md', () => {
    const changeDir = join(tempDir, 'invalid-capability-context');
    mkdirSync(changeDir, { recursive: true });
    writeValidPlanningArtifacts(changeDir);
    writeValidExecutionContract(changeDir);
    writeFileSync(join(changeDir, 'specs', 'rate-limit', 'context.md'), '# Rate Limit Context\n\n- **When changing counters**: Preserve atomic increments.\n');

    const result = runValidate(changeDir);

    assert.equal(result.exitCode, 1);
    assert.ok(result.stdout.includes('Capability markdown files must be named spec.md'));
  });

  it('fails when specs markdown is not placed at specs/<capability>/spec.md', () => {
    const changeDir = join(tempDir, 'misnamed-spec');
    mkdirSync(join(changeDir, 'specs'), { recursive: true });
    writeValidPlanningArtifacts(changeDir);
    rmSync(join(changeDir, 'specs'), { recursive: true, force: true });
    mkdirSync(join(changeDir, 'specs'), { recursive: true });
    writeFileSync(join(changeDir, 'specs', 'rate-limit.md'), '## ADDED Requirements\n\n### Requirement: Rate limit requests\n\nThe system SHALL reject requests that exceed the configured rate limit.\n\n#### Scenario: Request exceeds limit\n- **WHEN** a client sends too many requests\n- **THEN** the system returns a rate limit response\n');

    const result = runValidate(changeDir);

    assert.equal(result.exitCode, 1);
    assert.ok(result.stdout.includes('specs/rate-limit.md'));
    assert.ok(result.stdout.includes('Capability markdown files must be named spec.md'));
  });

  it('fails when requirement titles appear without a traceability table', () => {
    const changeDir = join(tempDir, 'contract-missing-requirement');
    mkdirSync(changeDir, { recursive: true });
    writeValidPlanningArtifacts(changeDir);
    writeValidExecutionContract(changeDir);
    writeFileSync(join(changeDir, 'execution-contract.md'), '# Execution Contract\n\n## Intent Lock\n\nAdd request protection.\n\n## Approved Behavior\n\nRate limit requests appears here but is not mapped.\n\n## Design Constraints\n\nUse shared middleware.\n\n## Task Batches\n\n### Batch 1\n\n- Add tests.\n\n## Test Obligations\n\n- Start with failing tests.\n\n## Review Gates\n\n- Review before closure.\n\n## Escalation Rules\n\n- Return to bridging if design changes.\n');

    const result = runValidate(changeDir);

    assert.equal(result.exitCode, 1);
    assert.ok(result.stdout.includes('Missing required section: ## Requirement Traceability'));
    assert.ok(result.stdout.includes('Missing Requirement Traceability table'));
  });

  it('fails when a traceability row omits test obligations', () => {
    const changeDir = join(tempDir, 'contract-empty-test-obligation');
    mkdirSync(changeDir, { recursive: true });
    writeValidPlanningArtifacts(changeDir);
    writeValidExecutionContract(changeDir);
    writeFileSync(join(changeDir, 'execution-contract.md'), '# Execution Contract\n\n## Intent Lock\n\nAdd request protection.\n\n## Approved Behavior\n\nRate limit requests when clients exceed configured limits.\n\n## Requirement Traceability\n\n| Requirement | Approved Behavior | Test Obligation | Batch |\n|---|---|---|---|\n| Rate limit requests | Reject over-limit requests before expensive handlers run |  | Batch 1 |\n\n## Design Constraints\n\nUse shared middleware.\n\n## Task Batches\n\n### Batch 1\n\n- Add tests.\n\n## Test Obligations\n\n- Start with failing tests.\n\n## Review Gates\n\n- Review before closure.\n\n## Escalation Rules\n\n- Return to bridging if design changes.\n');

    const result = runValidate(changeDir);

    assert.equal(result.exitCode, 1);
    assert.ok(result.stdout.includes('must map to non-empty Test Obligation'));
  });

  it('fails when a traceability row references a missing task batch', () => {
    const changeDir = join(tempDir, 'contract-missing-batch');
    mkdirSync(changeDir, { recursive: true });
    writeValidPlanningArtifacts(changeDir);
    writeValidExecutionContract(changeDir);
    writeFileSync(join(changeDir, 'execution-contract.md'), '# Execution Contract\n\n## Intent Lock\n\nAdd request protection.\n\n## Approved Behavior\n\nRate limit requests when clients exceed configured limits.\n\n## Requirement Traceability\n\n| Requirement | Approved Behavior | Test Obligation | Batch |\n|---|---|---|---|\n| Rate limit requests | Reject over-limit requests before expensive handlers run | Focused tests for HTTP 429 | Batch 9 |\n\n## Design Constraints\n\nUse shared middleware.\n\n## Task Batches\n\n### Batch 1\n\n- Add tests.\n\n## Test Obligations\n\n- Start with failing tests.\n\n## Review Gates\n\n- Review before closure.\n\n## Escalation Rules\n\n- Return to bridging if design changes.\n');

    const result = runValidate(changeDir);

    assert.equal(result.exitCode, 1);
    assert.ok(result.stdout.includes('references missing task batch: batch 9'));
  });
});
