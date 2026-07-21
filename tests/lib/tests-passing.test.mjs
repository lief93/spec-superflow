import { describe, it, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { checkTestsPassing } from '../../scripts/guard/checks/tests-passing.mjs';

let changeDir;

function writeState(result = 'pass', extra = '') {
  writeFileSync(join(changeDir, '.spec-superflow.yaml'), `test_result: ${result}\n${extra}`);
}

function writeFrontendContract(uiObligation = 'Run existing') {
  writeFileSync(join(changeDir, 'execution-contract.md'), `# Execution Contract
## Frontend Verification
- **Frontend Impact**: Yes
- **Reason**: The change affects a client screen.
| Check | Obligation | Scope | Target Environment | Command Or Procedure | Evidence Required |
|---|---|---|---|---|---|
| UI Test | ${uiObligation} | Changed screen | Android emulator | Run focused UI tests | Test report |
| Device Test | Required | Changed user path | Android emulator | Build, install, launch, and exercise path | Result log |
## Review Gates
- Review before closure.
`);
}

function writeFrontendSummary({ uiObligation = 'Run existing', uiResult = 'Pass', deviceResult = 'Pass' } = {}) {
  writeFileSync(join(changeDir, 'pr-summary.md'), `# PR Summary
## Frontend Verification Evidence
- **Frontend Impact**: Yes
- **Reason**: The change affects a client screen.
| Check | Planned Obligation | Result | Environment | Command Or Procedure | Evidence |
|---|---|---|---|---|---|
| UI Test | ${uiObligation} | ${uiResult} | Pixel API 35 emulator | ./gradlew connectedDebugAndroidTest | 4 passed, report/build/ui |
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
