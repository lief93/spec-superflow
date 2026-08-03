import { describe, it, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, readFileSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { checkTestsPassing } from '../../scripts/guard/checks/tests-passing.mjs';

let changeDir;

function writeState(result = 'pass', extra = '') {
  writeFileSync(join(changeDir, '.spec-superflow.yaml'), `test_result: ${result}\n${extra}`);
}

function writeFrontendContract(uiObligation = 'Run existing') {
  const testFile = uiObligation === 'Unavailable' ? 'Not configured' : '`app/src/androidTest/java/TransferResultTest.kt`';
  const testCase = uiObligation === 'Unavailable' ? 'Searched app/src/androidTest and Gradle test configuration; no UI runner exists' : '`showsTransferFailure`';
  writeFileSync(join(changeDir, 'execution-contract.md'), `# Execution Contract
## AC Test Matrix
| Requirement | AC | Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|---|---|
| Show transfer result | Transfer fails | UI | Android | ${uiObligation} | ${testFile} | ${testCase} | The user sees the transfer failure state and can retry. |
## Frontend Verification
- **Frontend Impact**: Yes
- **Reason**: The change affects a client screen.
| Check | Obligation | Scope | Target Environment | Command Or Procedure | Evidence Required |
|---|---|---|---|---|---|
| UI Test | Required by AC Test Matrix | Changed screen | Android emulator | Run focused UI tests | Test report |
| Device Test | Required | Changed user path | Android emulator | Build, install, launch, and exercise path | Result log |
## Review Gates
- Review before closure.
`);
}

function writeFrontendTasks(uiObligation = 'Run existing') {
  const testFile = uiObligation === 'Unavailable' ? 'Not configured' : '`app/src/androidTest/java/TransferResultTest.kt`';
  const testCase = uiObligation === 'Unavailable' ? 'Searched app/src/androidTest and Gradle test configuration; no UI runner exists' : '`showsTransferFailure`';
  writeFileSync(join(changeDir, 'tasks.md'), `# Tasks
## Batch 1: Show transfer result
### AC: Transfer fails
- **Requirement**: Show transfer result
- **User-visible**: Yes
#### File Changes
##### Modify \`app/src/main/java/TransferResult.kt\`
- **Change**: Show the transfer failure state and retry action.
#### TDD Test Plan
| Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|
| UI | Android | ${uiObligation} | ${testFile} | ${testCase} | The user sees the transfer failure state and can retry. |
### Batch Verification
- [ ] Run the focused UI test and relevant regression tests.
`);
}

function writeCompactFrontendContract() {
  writeFileSync(join(changeDir, 'execution-contract.md'), `# Execution Contract
## Approved Artifacts
- **Planning Lock**: \`.spec-superflow.yaml > artifacts_hash\`
## Execution Mode
- **Mode**: Inline
## Batch Gates
| Batch | Entry Gate | Exit Gate | Review Gate |
|---|---|---|---|
| Batch 1 | Approved | Tests pass | Review complete |
## Verification
| Check | Command Or Procedure | Evidence Required |
|---|---|---|
| AC tests | Run tasks.md TDD Test Plan | Exact case result |
## Frontend Verification
- **Frontend Impact**: Yes
- **Reason**: The change affects a client screen.
| Check | Obligation | Scope | Target Environment | Command Or Procedure | Evidence Required |
|---|---|---|---|---|---|
| UI Test | Required by tasks.md | Changed screen | Android emulator | Run focused UI tests | Test report |
| Device Test | Required | Changed user path | Android emulator | Build, install, launch, and exercise path | Result log |
## Stop Conditions
- Stop when a required check fails.
`);
}

function writeFrontendSummary({ uiObligation = 'Run existing', uiResult = 'Pass', deviceResult = 'Pass', plannedUiObligation = 'Required by AC Test Matrix' } = {}) {
  const testFile = uiObligation === 'Unavailable' ? 'Not configured' : '`app/src/androidTest/java/TransferResultTest.kt`';
  const testCase = uiObligation === 'Unavailable' ? 'Searched app/src/androidTest and Gradle test configuration; no UI runner exists' : '`showsTransferFailure`';
  writeFileSync(join(changeDir, 'pr-summary.md'), `# PR Summary
## AC Test Evidence
| Requirement | AC | Layer | Platform | Test File | Test Case | Result | Command | Evidence |
|---|---|---|---|---|---|---|---|---|
| Show transfer result | Transfer fails | UI | Android | ${testFile} | ${testCase} | ${uiResult} | ./gradlew connectedDebugAndroidTest | Named case result in report/build/ui |
## Frontend Verification Evidence
- **Frontend Impact**: Yes
- **Reason**: The change affects a client screen.
| Check | Planned Obligation | Result | Environment | Command Or Procedure | Evidence |
|---|---|---|---|---|---|
| UI Test | ${plannedUiObligation} | ${uiResult} | Pixel API 35 emulator | ./gradlew connectedDebugAndroidTest | 4 passed, report/build/ui |
| Device Test | Required | ${deviceResult} | Pixel API 35 emulator | Build, install, launch, and exercise changed path | Launch and interaction completed |
## Exceptions And Known Risks
- None.
`);
}

describe('tests-passing frontend evidence gate', () => {
  beforeEach(() => {
    changeDir = mkdtempSync(join(tmpdir(), 'ssf-tests-passing-'));
    writeState();
  });

  afterEach(() => {
    rmSync(changeDir, { recursive: true, force: true });
  });

  it('preserves legacy behavior when no frontend verification section exists', () => {
    assert.deepEqual(checkTestsPassing(changeDir), { pass: true, failures: [] });
  });

  it('fails when frontend work has no PR summary evidence', () => {
    writeFrontendContract();
    const result = checkTestsPassing(changeDir);
    assert.equal(result.pass, false);
    assert.match(result.failures.join('\n'), /pr-summary\.md does not exist/);
  });

  it('fails when the Device Test did not pass', () => {
    writeFrontendContract();
    writeFrontendSummary({ deviceResult: 'Fail' });
    const result = checkTestsPassing(changeDir);
    assert.equal(result.pass, false);
    assert.match(result.failures.join('\n'), /Device Test result is 'Fail'/);
  });

  it('passes when required UI and Device Test evidence is complete', () => {
    writeFrontendContract();
    writeFrontendSummary();
    assert.deepEqual(checkTestsPassing(changeDir), { pass: true, failures: [] });
  });

  it('rejects aggregate UI evidence when the AC-specific test row is missing', () => {
    writeFrontendContract();
    writeFrontendSummary();
    const summaryPath = join(changeDir, 'pr-summary.md');
    const summary = readFileSync(summaryPath, 'utf-8');
    writeFileSync(summaryPath, summary.replace(/## AC Test Evidence[\s\S]*?(?=## Frontend Verification Evidence)/, ''));
    const result = checkTestsPassing(changeDir);
    assert.equal(result.pass, false);
    assert.match(result.failures.join('\n'), /missing ## AC Test Evidence/);
  });

  it('accepts an evidenced and developer-confirmed UI capability gap while still requiring Device Test', () => {
    writeState('pass', 'dp_6_result: confirmed conditional: UI test capability unavailable\n');
    writeFrontendContract('Unavailable');
    writeFrontendSummary({ uiObligation: 'Unavailable', uiResult: 'Unavailable' });
    assert.deepEqual(checkTestsPassing(changeDir), { pass: true, failures: [] });
  });

  it('rejects an unavailable UI Test without developer confirmation', () => {
    writeFrontendContract('Unavailable');
    writeFrontendSummary({ uiObligation: 'Unavailable', uiResult: 'Unavailable' });
    const result = checkTestsPassing(changeDir);
    assert.equal(result.pass, false);
    assert.match(result.failures.join('\n'), /developer-confirmed conditional DP-6 decision/);
  });

  it('matches compact-contract evidence against tasks.md test plans', () => {
    writeFrontendTasks();
    writeCompactFrontendContract();
    writeFrontendSummary({ plannedUiObligation: 'Required by tasks.md' });

    assert.deepEqual(checkTestsPassing(changeDir), { pass: true, failures: [] });
  });

  it('fails compact-contract closure when tasks.md planned evidence is missing', () => {
    writeFrontendTasks();
    writeCompactFrontendContract();
    writeFrontendSummary({ plannedUiObligation: 'Required by tasks.md' });
    const summaryPath = join(changeDir, 'pr-summary.md');
    const summary = readFileSync(summaryPath, 'utf-8');
    writeFileSync(summaryPath, summary.replace(/## AC Test Evidence[\s\S]*?(?=## Frontend Verification Evidence)/, ''));

    const result = checkTestsPassing(changeDir);

    assert.equal(result.pass, false);
    assert.match(result.failures.join('\n'), /missing ## AC Test Evidence/);
  });
});
