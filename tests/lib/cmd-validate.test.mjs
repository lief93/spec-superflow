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
| Requirement | Scenario | Design Decision | Affected Area | Baseline / Reuse | Constraint / Deviation | Why Here |
|---|---|---|---|---|---|---|
| Rate limit requests | Request exceeds limit | Shared middleware | HTTP middleware | Existing route registration | No new handler contract | Middleware runs before expensive handlers |
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
- **User-visible**: No
#### File Changes
##### Create \`src/rate-limit.ts\`
- **Responsibility**: Enforce the shared request limit before handlers run.
- **Add**: Add the middleware entry point and bounded counter storage.
- **Used by**: HTTP route registration.
#### TDD Test Plan
| Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|
| Unit | Node | Add | \`test/rate-limit.test.ts\` | \`rejects over-limit requests\` | Over-limit requests are rejected before handlers run. |
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
  writeFileSync(join(changeDir, 'execution-contract.md'), '# Execution Contract\n\n## Intent Lock\n\nAdd request rate limiting.\n\n## Approved Behavior\n\nRate limit requests when clients exceed configured limits.\n\n## Requirement Traceability\n\n| Requirement | Approved Behavior | Test Obligation | Batch |\n|---|---|---|---|\n| Rate limit requests | Reject over-limit requests before expensive handlers run | Focused tests for HTTP 429 and service-call prevention | Batch 1 |\n\n## AC Test Matrix\n\n| Requirement | AC | Layer | Platform | Action | Test File | Test Case | Proves |\n|---|---|---|---|---|---|---|---|\n| Rate limit requests | Request exceeds limit | Unit | Node | Add | `test/rate-limit.test.ts` | `rejects over-limit requests` | Over-limit requests are rejected before handlers run. |\n\n## Design Constraints\n\nUse shared middleware.\n\n## Task Batches\n\n### Batch 1\n\n- Add tests and middleware.\n\n## Test Obligations\n\n- Start with failing tests for Rate limit requests.\n\n## Frontend Verification\n\n- **Frontend Impact**: No\n- **Reason**: This change only affects server-side HTTP middleware.\n\n## Execution Mode\n\n- Mode: Inline\n\n## Verification Dimensions\n\n| Dimension | Status | Findings |\n|---|---|---|\n| Completeness | Pending | - |\n\n## Review Gates\n\n- Review before closure.\n\n## Escalation Rules\n\n- Return to bridging if middleware shape changes.\n');
}

function writeCompactExecutionContract(changeDir) {
  writeFileSync(join(changeDir, 'execution-contract.md'), `# Execution Contract

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
- **Selection rationale**: One isolated middleware batch.

## Batch Gates

| Batch | Entry Gate | Exit Gate | Review Gate |
|---|---|---|---|
| Batch 1 | Approved planning lock | Planned tests pass and files match tasks.md | Review the completed batch |

## Verification

| Check | Command Or Procedure | Evidence Required |
|---|---|---|
| AC tests | Run every row in tasks.md TDD Test Plan | Exact case result |
| Regression | \`npm test\` | Zero failures |

## Frontend Verification

- **Frontend Impact**: No
- **Reason**: This change only affects server-side HTTP middleware.

## Stop Conditions

- Stop when the planning hash changes, an approved assumption fails, or a required test cannot run.
`);
}

function writeFrontendVerification(changeDir, rows) {
  const contractPath = join(changeDir, 'execution-contract.md');
  const contract = readFileSync(contractPath, 'utf-8');
  const section = `## Frontend Verification

- **Frontend Impact**: Yes
- **Reason**: The change affects a user-visible client screen.

| Check | Obligation | Scope | Target Environment | Command Or Procedure | Evidence Required |
|---|---|---|---|---|---|
${rows}
`;
  writeFileSync(contractPath, contract.replace(/## Frontend Verification[\s\S]*?(?=\n## Execution Mode)/, section));
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
    mkdirSync(join(tempDir, '.git'));
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

  it('accepts a compact execution lock without copied planning matrices', () => {
    const changeDir = join(tempDir, 'compact-contract');
    mkdirSync(changeDir, { recursive: true });
    writeValidPlanningArtifacts(changeDir);
    const tasksPath = join(changeDir, 'tasks.md');
    writeFileSync(
      tasksPath,
      readFileSync(tasksPath, 'utf-8')
        .replace('- **Responsibility**: Enforce the shared request limit before handlers run.', '- **Why this file**: A dedicated middleware owns admission before handlers.\n- **Responsibility**: Enforce the shared request limit before handlers run.')
        .replace(
          /#### TDD Steps[\s\S]*$/,
          '### Batch Verification\n- [ ] **RED / Baseline**: Run `node --test test/rate-limit.test.ts`; expect behavior-specific failure.\n- [ ] **GREEN**: Run `node --test test/rate-limit.test.ts`; expect PASS.\n- [ ] **Regression**: Run `npm test`; expect zero failures.\n',
        ),
    );
    writeCompactExecutionContract(changeDir);

    const result = runValidate(changeDir);

    assert.equal(result.exitCode, 0, result.stdout || result.stderr);
    assert.ok(result.stdout.includes('All artifacts validated'));
  });

  it('rejects a compact contract that omits a tasks batch gate', () => {
    const changeDir = join(tempDir, 'compact-contract-missing-batch');
    mkdirSync(changeDir, { recursive: true });
    writeValidPlanningArtifacts(changeDir);
    writeCompactExecutionContract(changeDir);
    const contractPath = join(changeDir, 'execution-contract.md');
    writeFileSync(contractPath, readFileSync(contractPath, 'utf-8').replace('| Batch 1 | Approved planning lock | Planned tests pass and files match tasks.md | Review the completed batch |', ''));

    const result = runValidate(changeDir);

    assert.equal(result.exitCode, 1);
    assert.match(result.stdout, /Batch Gates is missing tasks\.md batch: Batch 1/);
  });

  it('rejects a slim task file that does not explain why each file is changed', () => {
    const changeDir = join(tempDir, 'slim-tasks-missing-file-rationale');
    mkdirSync(changeDir, { recursive: true });
    writeValidPlanningArtifacts(changeDir);
    const tasksPath = join(changeDir, 'tasks.md');
    writeFileSync(
      tasksPath,
      readFileSync(tasksPath, 'utf-8').replace(
        /#### TDD Steps[\s\S]*$/,
        '### Batch Verification\n- [ ] Run `node --test test/rate-limit.test.ts`; expect PASS.\n',
      ),
    );
    writeCompactExecutionContract(changeDir);

    const result = runValidate(changeDir);

    assert.equal(result.exitCode, 1);
    assert.match(result.stdout, /needs a concrete Why this file explanation/);
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

  it('accepts a legacy five-column design coverage table', () => {
    const changeDir = join(tempDir, 'legacy-design-columns');
    mkdirSync(changeDir, { recursive: true });
    writeValidPlanningArtifacts(changeDir);
    writeValidExecutionContract(changeDir);
    const designPath = join(changeDir, 'design.md');
    writeFileSync(
      designPath,
      readFileSync(designPath, 'utf-8')
        .replace(
          '| Requirement | Scenario | Design Decision | Affected Area | Baseline / Reuse | Constraint / Deviation | Why Here |',
          '| Requirement | Scenario | Design Decision | Affected Area | Why Here |',
        )
        .replace('|---|---|---|---|---|---|---|', '|---|---|---|---|---|')
        .replace(
          '| Rate limit requests | Request exceeds limit | Shared middleware | HTTP middleware | Existing route registration | No new handler contract | Middleware runs before expensive handlers |',
          '| Rate limit requests | Request exceeds limit | Shared middleware | HTTP middleware | Middleware runs before expensive handlers |',
        ),
    );

    const result = runValidate(changeDir);

    assert.equal(result.exitCode, 0, result.stdout || result.stderr);
    assert.match(result.stdout, /All artifacts validated/);
  });

  it('rejects non-meaningful baseline or constraint coverage', () => {
    const changeDir = join(tempDir, 'design-empty-new-columns');
    mkdirSync(changeDir, { recursive: true });
    writeValidPlanningArtifacts(changeDir);
    writeValidExecutionContract(changeDir);
    const designPath = join(changeDir, 'design.md');
    writeFileSync(
      designPath,
      readFileSync(designPath, 'utf-8').replace(
        '| Existing route registration | No new handler contract |',
        '| TBD | N/A |',
      ),
    );

    const result = runValidate(changeDir);

    assert.equal(result.exitCode, 1);
    assert.match(result.stdout, /requires baseline \/ reuse/i);
    assert.match(result.stdout, /requires constraint \/ deviation/i);
  });

  it('accepts None when there is no design constraint or deviation', () => {
    const changeDir = join(tempDir, 'design-no-constraint');
    mkdirSync(changeDir, { recursive: true });
    writeValidPlanningArtifacts(changeDir);
    writeValidExecutionContract(changeDir);
    const designPath = join(changeDir, 'design.md');
    writeFileSync(
      designPath,
      readFileSync(designPath, 'utf-8').replace(
        '| Existing route registration | No new handler contract |',
        '| Existing route registration | None |',
      ),
    );

    const result = runValidate(changeDir);

    assert.equal(result.exitCode, 0, result.stdout || result.stderr);
    assert.match(result.stdout, /All artifacts validated/);
  });

  it('rejects a compact contract that does not lock design.md', () => {
    const changeDir = join(tempDir, 'compact-contract-missing-design');
    mkdirSync(changeDir, { recursive: true });
    writeValidPlanningArtifacts(changeDir);
    writeCompactExecutionContract(changeDir);
    const contractPath = join(changeDir, 'execution-contract.md');
    writeFileSync(
      contractPath,
      readFileSync(contractPath, 'utf-8').replace('| Design | `design.md` |\n', ''),
    );

    const result = runValidate(changeDir);

    assert.equal(result.exitCode, 1);
    assert.match(result.stdout, /Approved Artifacts must reference design\.md/);
  });

  it('accepts a configured design skip in a compact contract', () => {
    const changeDir = join(tempDir, 'compact-contract-design-skip');
    mkdirSync(changeDir, { recursive: true });
    writeValidPlanningArtifacts(changeDir);
    rmSync(join(changeDir, 'design.md'));
    writeFileSync(join(changeDir, 'spec-superflow.config.json'), JSON.stringify({ artifacts: { skip: ['design'] } }));
    const tasksPath = join(changeDir, 'tasks.md');
    writeFileSync(
      tasksPath,
      readFileSync(tasksPath, 'utf-8')
        .replace('- **Responsibility**: Enforce the shared request limit before handlers run.', '- **Why this file**: A dedicated middleware owns admission before handlers.\n- **Responsibility**: Enforce the shared request limit before handlers run.')
        .replace(
          /#### TDD Steps[\s\S]*$/,
          '### Batch Verification\n- [ ] **RED / Baseline**: Run `node --test test/rate-limit.test.ts`; expect behavior-specific failure.\n- [ ] **GREEN**: Run `node --test test/rate-limit.test.ts`; expect PASS.\n- [ ] **Regression**: Run `npm test`; expect zero failures.\n',
        ),
    );
    writeCompactExecutionContract(changeDir);
    const contractPath = join(changeDir, 'execution-contract.md');
    writeFileSync(
      contractPath,
      readFileSync(contractPath, 'utf-8').replace('| Design | `design.md` |', '| Design | configured skip |'),
    );

    const result = runValidate(changeDir);

    assert.equal(result.exitCode, 0, result.stdout || result.stderr);
    assert.match(result.stdout, /All artifacts validated/);
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
| Requirement | Scenario | Design Decision | Affected Area | Baseline / Reuse | Constraint / Deviation | Why Here |
|---|---|---|---|---|---|---|
| Rate limit requests | Normal request | Shared middleware | HTTP middleware | Existing route registration | No new handler contract | Middleware owns request admission |
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

  it('fails when an AC omits its TDD Test Plan', () => {
    const changeDir = join(tempDir, 'tasks-missing-test-coverage');
    mkdirSync(changeDir, { recursive: true });
    writeValidPlanningArtifacts(changeDir);
    writeValidExecutionContract(changeDir);
    const tasksPath = join(changeDir, 'tasks.md');
    const tasks = readFileSync(tasksPath, 'utf-8');
    writeFileSync(tasksPath, tasks.replace(/#### TDD Test Plan[\s\S]*?(?=#### TDD Steps)/, ''));

    const result = runValidate(changeDir);

    assert.equal(result.exitCode, 1);
    assert.ok(result.stdout.includes('is missing #### TDD Test Plan'));
  });

  it('fails when an AC uses an unsupported TDD test action', () => {
    const changeDir = join(tempDir, 'tasks-invalid-ui-test-action');
    mkdirSync(changeDir, { recursive: true });
    writeValidPlanningArtifacts(changeDir);
    writeValidExecutionContract(changeDir);
    const tasksPath = join(changeDir, 'tasks.md');
    const tasks = readFileSync(tasksPath, 'utf-8');
    writeFileSync(tasksPath, tasks.replace('| Unit | Node | Add |', '| UI | Web | Maybe |'));

    const result = runValidate(changeDir);

    assert.equal(result.exitCode, 1);
    assert.ok(result.stdout.includes('Action must be Add, Update, Run existing, or Unavailable'));
  });

  it('rejects a markdown document used as a test file', () => {
    const changeDir = join(tempDir, 'tasks-markdown-as-test');
    mkdirSync(changeDir, { recursive: true });
    writeValidPlanningArtifacts(changeDir);
    writeValidExecutionContract(changeDir);
    const tasksPath = join(changeDir, 'tasks.md');
    const tasks = readFileSync(tasksPath, 'utf-8');
    writeFileSync(tasksPath, tasks.replace('`test/rate-limit.test.ts`', '`docs/rate-limit-evidence.md`'));

    const result = runValidate(changeDir);

    assert.equal(result.exitCode, 1);
    assert.ok(result.stdout.includes('Test File must be a platform test source file'));
  });

  for (const extension of ['cjs', 'mjs']) {
    it(`accepts a Node.js ${extension} test source file`, () => {
      const changeDir = join(tempDir, `tasks-${extension}-test`);
      mkdirSync(changeDir, { recursive: true });
      writeValidPlanningArtifacts(changeDir);
      writeValidExecutionContract(changeDir);
      for (const fileName of ['tasks.md', 'execution-contract.md']) {
        const path = join(changeDir, fileName);
        writeFileSync(
          path,
          readFileSync(path, 'utf-8').replace(
            '`test/rate-limit.test.ts`',
            `\`tests/rate-limit.test.${extension}\``,
          ),
        );
      }

      const result = runValidate(changeDir);

      assert.equal(result.exitCode, 0, result.stdout);
    });
  }

  it('requires a UI test row for a user-visible AC', () => {
    const changeDir = join(tempDir, 'tasks-visible-ac-without-ui');
    mkdirSync(changeDir, { recursive: true });
    writeValidPlanningArtifacts(changeDir);
    writeValidExecutionContract(changeDir);
    const tasksPath = join(changeDir, 'tasks.md');
    const tasks = readFileSync(tasksPath, 'utf-8');
    writeFileSync(tasksPath, tasks.replace('- **User-visible**: No', '- **User-visible**: Yes'));

    const result = runValidate(changeDir);

    assert.equal(result.exitCode, 1);
    assert.ok(result.stdout.includes('is user-visible and requires an AC-specific UI test row'));
  });

  it('requires Run existing to name a real test file', () => {
    const changeDir = join(tempDir, 'tasks-missing-existing-test');
    mkdirSync(changeDir, { recursive: true });
    writeValidPlanningArtifacts(changeDir);
    writeValidExecutionContract(changeDir);
    const tasksPath = join(changeDir, 'tasks.md');
    const tasks = readFileSync(tasksPath, 'utf-8');
    writeFileSync(tasksPath, tasks.replace('| Unit | Node | Add |', '| Unit | Node | Run existing |'));

    const result = runValidate(changeDir);

    assert.equal(result.exitCode, 1);
    assert.ok(result.stdout.includes('Run existing requires an existing test file: test/rate-limit.test.ts'));
  });

  it('accepts Run existing when the test file and case both exist', () => {
    const changeDir = join(tempDir, 'tasks-real-existing-test');
    mkdirSync(changeDir, { recursive: true });
    mkdirSync(join(tempDir, 'test'), { recursive: true });
    writeFileSync(join(tempDir, 'test', 'existing-rate-limit.test.ts'), "it('rejects existing over-limit requests', () => {});\n");
    writeValidPlanningArtifacts(changeDir);
    writeValidExecutionContract(changeDir);
    const oldRow = '| Unit | Node | Add | `test/rate-limit.test.ts` | `rejects over-limit requests` | Over-limit requests are rejected before handlers run. |';
    const newRow = '| Unit | Node | Run existing | `test/existing-rate-limit.test.ts` | `rejects existing over-limit requests` | Over-limit requests are rejected before handlers run. |';
    const tasksPath = join(changeDir, 'tasks.md');
    writeFileSync(tasksPath, readFileSync(tasksPath, 'utf-8').replace(oldRow, newRow));
    const contractPath = join(changeDir, 'execution-contract.md');
    const oldContractRow = '| Rate limit requests | Request exceeds limit | Unit | Node | Add | `test/rate-limit.test.ts` | `rejects over-limit requests` | Over-limit requests are rejected before handlers run. |';
    const newContractRow = '| Rate limit requests | Request exceeds limit | Unit | Node | Run existing | `test/existing-rate-limit.test.ts` | `rejects existing over-limit requests` | Over-limit requests are rejected before handlers run. |';
    writeFileSync(contractPath, readFileSync(contractPath, 'utf-8').replace(oldContractRow, newContractRow));

    const result = runValidate(changeDir);

    assert.equal(result.exitCode, 0, result.stderr);
    assert.ok(result.stdout.includes('All artifacts validated'));
  });

  it('preserves underscores in existing test file and case names', () => {
    const changeDir = join(tempDir, 'tasks-existing-test-with-underscores');
    mkdirSync(changeDir, { recursive: true });
    mkdirSync(join(tempDir, 'test'), { recursive: true });
    writeFileSync(
      join(tempDir, 'test', 'existing_rate_limit_test.ts'),
      'function rejects_existing_over_limit_requests() {}\n',
    );
    writeValidPlanningArtifacts(changeDir);
    writeValidExecutionContract(changeDir);

    const oldTaskRow = '| Unit | Node | Add | `test/rate-limit.test.ts` | `rejects over-limit requests` | Over-limit requests are rejected before handlers run. |';
    const newTaskRow = '| Unit | Node | Run existing | `test/existing_rate_limit_test.ts` | `rejects_existing_over_limit_requests` | Over-limit requests are rejected before handlers run. |';
    const tasksPath = join(changeDir, 'tasks.md');
    writeFileSync(tasksPath, readFileSync(tasksPath, 'utf-8').replace(oldTaskRow, newTaskRow));

    const oldContractRow = '| Rate limit requests | Request exceeds limit | Unit | Node | Add | `test/rate-limit.test.ts` | `rejects over-limit requests` | Over-limit requests are rejected before handlers run. |';
    const newContractRow = '| Rate limit requests | Request exceeds limit | Unit | Node | Run existing | `test/existing_rate_limit_test.ts` | `rejects_existing_over_limit_requests` | Over-limit requests are rejected before handlers run. |';
    const contractPath = join(changeDir, 'execution-contract.md');
    writeFileSync(
      contractPath,
      readFileSync(contractPath, 'utf-8').replace(oldContractRow, newContractRow),
    );

    const result = runValidate(changeDir);

    assert.equal(result.exitCode, 0, result.stderr);
    assert.ok(result.stdout.includes('All artifacts validated'));
  });

  it('rejects an Android UI test outside src/androidTest', () => {
    const changeDir = join(tempDir, 'tasks-invalid-android-ui-location');
    mkdirSync(changeDir, { recursive: true });
    writeValidPlanningArtifacts(changeDir);
    writeValidExecutionContract(changeDir);
    const tasksPath = join(changeDir, 'tasks.md');
    const tasks = readFileSync(tasksPath, 'utf-8');
    writeFileSync(tasksPath, tasks
      .replace('- **User-visible**: No', '- **User-visible**: Yes')
      .replace(
        '| Unit | Node | Add | `test/rate-limit.test.ts` | `rejects over-limit requests` | Over-limit requests are rejected before handlers run. |',
        '| UI | Android | Add | `app/src/test/java/RateLimitUiTest.kt` | `showsRateLimitError` | The user sees the rate-limit error after exceeding the limit. |',
      ));

    const result = runValidate(changeDir);

    assert.equal(result.exitCode, 1);
    assert.ok(result.stdout.includes('UI Test File does not match the declared platform test location'));
  });

  it('fails when the execution contract drops an AC test obligation', () => {
    const changeDir = join(tempDir, 'contract-drops-ac-test');
    mkdirSync(changeDir, { recursive: true });
    writeValidPlanningArtifacts(changeDir);
    writeValidExecutionContract(changeDir);
    const contractPath = join(changeDir, 'execution-contract.md');
    const contract = readFileSync(contractPath, 'utf-8');
    const matrixRow = '| Rate limit requests | Request exceeds limit | Unit | Node | Add | `test/rate-limit.test.ts` | `rejects over-limit requests` | Over-limit requests are rejected before handlers run. |';
    writeFileSync(contractPath, contract.replace(matrixRow, ''));

    const result = runValidate(changeDir);

    assert.equal(result.exitCode, 1);
    assert.ok(result.stdout.includes('AC Test Matrix is missing tasks.md obligation'));
  });

  it('accepts Unit and UI as layers in the same AC TDD plan', () => {
    const changeDir = join(tempDir, 'tasks-unit-and-ui-layers');
    mkdirSync(changeDir, { recursive: true });
    writeValidPlanningArtifacts(changeDir);
    writeValidExecutionContract(changeDir);
    const tasksPath = join(changeDir, 'tasks.md');
    const tasks = readFileSync(tasksPath, 'utf-8');
    writeFileSync(tasksPath, tasks
      .replace('- **User-visible**: No', '- **User-visible**: Yes')
      .replace(
        '| Unit | Node | Add | `test/rate-limit.test.ts` | `rejects over-limit requests` | Over-limit requests are rejected before handlers run. |',
        '| Unit | Node | Add | `test/rate-limit.test.ts` | `rejects over-limit requests` | Limit decisions reject oversized requests. |\n| UI | Web | Add | `ui/rate-limit.spec.ts` | `shows rejection` | The user sees the rejection state after exceeding the limit. |',
      ));
    const contractPath = join(changeDir, 'execution-contract.md');
    const contract = readFileSync(contractPath, 'utf-8');
    writeFileSync(contractPath, contract.replace(
      '| Rate limit requests | Request exceeds limit | Unit | Node | Add | `test/rate-limit.test.ts` | `rejects over-limit requests` | Over-limit requests are rejected before handlers run. |',
      '| Rate limit requests | Request exceeds limit | Unit | Node | Add | `test/rate-limit.test.ts` | `rejects over-limit requests` | Limit decisions reject oversized requests. |\n| Rate limit requests | Request exceeds limit | UI | Web | Add | `ui/rate-limit.spec.ts` | `shows rejection` | The user sees the rejection state after exceeding the limit. |',
    ));
    writeFrontendVerification(changeDir, [
      '| UI Test | Required by AC Test Matrix | Rate-limit screen | Desktop browser | npm run test:ui -- rate-limit | Test report path |',
      '| Device Test | Required | Changed user path | Chrome desktop | Launch and exercise the changed path | Manual evidence note |',
    ].join('\n'));

    const result = runValidate(changeDir);

    assert.equal(result.exitCode, 0, result.stderr);
    assert.ok(result.stdout.includes('All artifacts validated'));
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
- **User-visible**: No
#### File Changes
##### Modify \`src/rate-limit.ts\`
- **Change**: Adjust the existing response text without changing middleware behavior.
#### TDD Test Plan
| Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|
| Unit | Node | Add | \`test/rate-limit-copy.test.ts\` | \`returns revised copy\` | The middleware returns the revised response text. |
#### TDD Steps
- [ ] Update the focused assertion and implementation text.
`);
    const contractPath = join(changeDir, 'execution-contract.md');
    const contract = readFileSync(contractPath, 'utf-8');
    writeFileSync(contractPath, contract.replace(
      '| Rate limit requests | Request exceeds limit | Unit | Node | Add | `test/rate-limit.test.ts` | `rejects over-limit requests` | Over-limit requests are rejected before handlers run. |',
      '| Rate limit requests | Request exceeds limit | Unit | Node | Add | `test/rate-limit-copy.test.ts` | `returns revised copy` | The middleware returns the revised response text. |',
    ));

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
- **User-visible**: No
#### File Changes
##### Create \`src/rate-limit.ts\`
- **Add**: Add the shared middleware.
#### TDD Test Plan
| Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|
| Unit | Node | Add | \`test/rate-limit.test.ts\` | \`rejects over-limit requests\` | The middleware rejects over-limit requests. |
#### TDD Steps
- [ ] Add focused tests and implementation.
## Batch 2: Repeat request rate limiting
### AC: Request exceeds limit
- **Requirement**: Rate limit requests
- **User-visible**: No
#### File Changes
##### Modify \`src/rate-limit.ts\`
- **Change**: Repeat the same behavior in another batch.
#### TDD Test Plan
| Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|
| Unit | Node | Add | \`test/rate-limit-repeat.test.ts\` | \`rejects over-limit requests again\` | The repeated behavior remains covered. |
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

  it('fails when frontend verification omits the Device Test row', () => {
    const changeDir = join(tempDir, 'frontend-missing-device-test');
    mkdirSync(changeDir, { recursive: true });
    writeValidPlanningArtifacts(changeDir);
    writeValidExecutionContract(changeDir);
    writeFrontendVerification(changeDir, '| UI Test | Required by AC Test Matrix | Rate-limit screen | Desktop browser | npm run test:ui -- rate-limit | Test report path |');

    const result = runValidate(changeDir);

    assert.equal(result.exitCode, 1);
    assert.ok(result.stdout.includes('Frontend Verification requires a Device Test row'));
  });

  it('fails when frontend Device Test is not required', () => {
    const changeDir = join(tempDir, 'frontend-device-test-optional');
    mkdirSync(changeDir, { recursive: true });
    writeValidPlanningArtifacts(changeDir);
    writeValidExecutionContract(changeDir);
    writeFrontendVerification(changeDir, [
      '| UI Test | Required by AC Test Matrix | Rate-limit screen | Desktop browser | npm run test:ui -- rate-limit | Test report path |',
      '| Device Test | Optional | Changed user path | Chrome desktop | Launch and exercise the changed path | Manual evidence note |',
    ].join('\n'));

    const result = runValidate(changeDir);

    assert.equal(result.exitCode, 1);
    assert.ok(result.stdout.includes('Device Test obligation must be Required for frontend work'));
  });
});
