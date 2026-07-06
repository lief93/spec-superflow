// tests/lib/cmd-sync.test.mjs
// Tests for scripts/lib/cmd-sync.mjs
import { describe, it, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { execFileSync } from 'node:child_process';
import { mkdtempSync } from 'node:fs';

const CLI_PATH = join(process.cwd(), 'scripts/spec-superflow.mjs');
let projectDir;

function writeChangeSpec(changeName, specName, content) {
  const specDir = join(projectDir, 'changes', changeName, 'specs', specName);
  mkdirSync(specDir, { recursive: true });
  writeFileSync(join(specDir, 'spec.md'), content);
  return join(projectDir, 'changes', changeName);
}

function validDelta(extra = '') {
  return `${extra}## ADDED Requirements

### Requirement: Show order detail

The system SHALL show order details to authorized users.

#### Scenario: Authorized user views order
- **WHEN** an authorized user opens an order detail
- **THEN** the system shows the order details
`;
}

function runSync(changeDir) {
  try {
    const stdout = execFileSync(process.execPath, [CLI_PATH, 'sync', changeDir], {
      cwd: projectDir,
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

describe('cmd-sync', () => {
  beforeEach(() => {
    projectDir = mkdtempSync(join(tmpdir(), 'ssf-sync-test-'));
  });

  afterEach(() => {
    if (projectDir) rmSync(projectDir, { recursive: true, force: true });
  });

  it('syncs to Canonical Target when a change spec declares one', () => {
    const content = validDelta(`## Canonical Target

- Path: \`specs/order/page-detail/spec.md\`
- Taxonomy: Order -> Page -> Detail

`);
    const changeDir = writeChangeSpec('add-order-detail', 'order-page-detail', content);

    const result = runSync(changeDir);

    assert.equal(result.exitCode, 0, result.stderr);
    assert.ok(result.stdout.includes('specs/order/page-detail/spec.md'));
    assert.ok(result.stdout.includes('Canonical Target'));
    assert.equal(readFileSync(join(projectDir, 'specs', 'order', 'page-detail', 'spec.md'), 'utf-8'), content);
    assert.equal(existsSync(join(projectDir, 'specs', 'order-page-detail', 'spec.md')), false);
  });

  it('keeps legacy relative-path sync when Canonical Target is absent', () => {
    const content = validDelta();
    const changeDir = writeChangeSpec('add-rate-limit', 'rate-limit', content);

    const result = runSync(changeDir);

    assert.equal(result.exitCode, 0, result.stderr);
    assert.ok(result.stdout.includes('specs/rate-limit/spec.md'));
    assert.equal(readFileSync(join(projectDir, 'specs', 'rate-limit', 'spec.md'), 'utf-8'), content);
  });

  it('rejects Canonical Target paths outside specs/', () => {
    const content = validDelta(`## Canonical Target

- Path: \`docs/order/page-detail/spec.md\`

`);
    const changeDir = writeChangeSpec('bad-target', 'order-page-detail', content);

    const result = runSync(changeDir);

    assert.notEqual(result.exitCode, 0);
    assert.ok(result.stderr.includes('Invalid Canonical Target'));
  });
});
