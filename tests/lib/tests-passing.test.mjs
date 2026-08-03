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

function writeFrontendSummary({
  uiObligation = 'Run existing',
  uiResult = 'Pass',
  deviceResult = 'Pass',
  environment = 'Pixel API 35 emulator',
} = {}) {
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
| UI Test | Required by AC Test Matrix | ${uiResult} | ${environment} | ./gradlew connectedDebugAndroidTest | 4 passed, report/build/ui |
| Device Test | Required | ${deviceResult} | ${environment} | Build, install, launch, and exercise changed path | Launch and interaction completed |
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

  it('continues to accept ordinary Android emulator evidence', () => {
    writeFrontendContract();
    writeFrontendSummary({ environment: 'Android emulator' });
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
});
