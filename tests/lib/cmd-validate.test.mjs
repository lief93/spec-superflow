// tests/lib/cmd-validate.test.mjs
// Tests for scripts/lib/cmd-validate.mjs
import { describe, it, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, mkdirSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { execFileSync } from 'node:child_process';

const CLI_PATH = join(process.cwd(), 'scripts/spec-superflow.mjs');
let tempDir;

function writeValidPlanningArtifacts(changeDir) {
  mkdirSync(join(changeDir, 'specs', 'rate-limit'), { recursive: true });
  writeFileSync(join(changeDir, 'proposal.md'), '## Why\nRate limiting is needed to protect shared resources from abusive bursts while keeping normal user traffic reliable.\n## What Changes\n- Add request rate limiting.');
  writeFileSync(join(changeDir, 'design.md'), '# Design\n## Context\nRate limiting runs before expensive handlers.\n## Decisions\n### Decision 1\n- Choice: Shared middleware\n- Rationale: It keeps enforcement consistent across endpoints.\n');
  writeFileSync(join(changeDir, 'tasks.md'), '# Tasks\n## File Structure\n- Create: src/rate-limit.ts\n## Tasks\n- [ ] Add failing tests\n- [ ] Implement middleware\n');
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
