// tests/lib/cmd-inject.test.mjs
// Tests for scripts/lib/cmd-inject.mjs
import { describe, it, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { join } from 'node:path';
import { mkdtempSync, writeFileSync, mkdirSync, rmSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { execFileSync } from 'node:child_process';

let generatePhaseGuard, toCursorMdc, toCopilotInstructions;
const CLI_PATH = join(process.cwd(), 'scripts/spec-superflow.mjs');

describe('cmd-inject: generatePhaseGuard()', () => {
  before(async () => {
    const modulePath = join(process.cwd(), 'scripts/lib/cmd-inject.mjs');
    const mod = await import(modulePath);
    generatePhaseGuard = mod.generatePhaseGuard;
    toCursorMdc = mod.toCursorMdc;
    toCopilotInstructions = mod.toCopilotInstructions;
  });

  it('replaces {{change_name}} placeholder', () => {
    const result = generatePhaseGuard({ state: 'exploring', change_name: 'add-csv-export' });
    assert.ok(result.includes('add-csv-export'), `Expected "add-csv-export" in output, got: ${result.substring(0, 100)}`);
  });

  it('replaces {{state}} placeholder', () => {
    const result = generatePhaseGuard({ state: 'executing', change_name: 'test' });
    assert.ok(result.includes('executing'));
  });

  it('replaces {{workflow}} placeholder', () => {
    const result = generatePhaseGuard({ state: 'exploring', workflow: 'hotfix', change_name: 'test' });
    assert.ok(result.includes('hotfix'));
  });

  it('generates exploring phase with allowed operations', () => {
    const result = generatePhaseGuard({ state: 'exploring', change_name: 'test' });
    assert.ok(result.includes('澄清需求'));
    assert.ok(result.includes('禁止操作'));
  });

  it('generates specifying phase with allowed operations', () => {
    const result = generatePhaseGuard({ state: 'specifying', change_name: 'test' });
    assert.ok(result.includes('specs/'));
    assert.ok(result.includes('design.md'));
  });

  it('generates bridging phase with contract operations', () => {
    const result = generatePhaseGuard({ state: 'bridging', change_name: 'test' });
    assert.ok(result.includes('execution-contract.md'));
    assert.ok(result.includes('ssf validate'));
  });

  it('generates approved-for-build phase', () => {
    const result = generatePhaseGuard({ state: 'approved-for-build', change_name: 'test' });
    assert.ok(result.includes('执行模式'));
    assert.ok(result.includes('DP-4'));
  });

  it('generates executing phase with test prohibition', () => {
    const result = generatePhaseGuard({ state: 'executing', change_name: 'test' });
    assert.ok(result.includes('跳过测试'));
  });

  it('generates debugging phase with root cause analysis', () => {
    const result = generatePhaseGuard({ state: 'debugging', change_name: 'test' });
    assert.ok(result.includes('根因分析'));
    assert.ok(result.includes('TDD 修复循环'));
  });

  it('generates closing phase with verification', () => {
    const result = generatePhaseGuard({ state: 'closing', change_name: 'test' });
    assert.ok(result.includes('三维验证'));
    assert.ok(result.includes('DP-7'));
  });

  it('generates abandoned terminal state', () => {
    const result = generatePhaseGuard({ state: 'abandoned', change_name: 'test' });
    assert.ok(result.includes('终止状态'));
    assert.ok(result.includes('不得合并'));
  });

  it('falls back to exploring for unknown state', () => {
    const result = generatePhaseGuard({ state: 'unknown-state', change_name: 'test' });
    assert.ok(result.includes('澄清需求'), `Expected exploring fallback, got: ${result.substring(0, 200)}`);
  });

  it('uses defaults when optional fields missing', () => {
    const result = generatePhaseGuard({ state: 'exploring' });
    // change_name defaults to 'unknown'
    assert.ok(result.includes('unknown'));
    // workflow defaults to 'full'
    assert.ok(result.includes('full'));
  });
});

describe('cmd-inject: toCursorMdc()', () => {
  it('wraps base content with Cursor MDC frontmatter', () => {
    const base = '# Phase Guard: test-change\n\n## Allowed\n- Do stuff';
    const result = toCursorMdc(base);

    assert.ok(result.includes('---'), 'Should have frontmatter delimiter');
    assert.ok(result.includes('description: spec-superflow phase guard'));
    assert.ok(result.includes('alwaysApply: true'));
    assert.ok(result.includes('test-change'));
  });
});

describe('cmd-inject: toCopilotInstructions()', () => {
  it('simplifies heading for Copilot format', () => {
    const base = '# Phase Guard: test-change\n\n## Allowed\n- Do stuff';
    const result = toCopilotInstructions(base);

    assert.ok(result.includes('# Phase Guard'));
    assert.ok(result.includes('## Allowed'));
    // Should NOT contain the change name in heading
    assert.ok(!result.includes('# Phase Guard: test-change'));
  });
});

describe('cmd-inject: CLI platform selection', () => {
  let tempDir;

  before(() => {
    tempDir = mkdtempSync(join(tmpdir(), 'ssf-inject-cli-'));
  });

  after(() => {
    if (tempDir) rmSync(tempDir, { recursive: true, force: true });
  });

  function makeChangeDir(name) {
    const changeDir = join(tempDir, 'changes', name);
    mkdirSync(changeDir, { recursive: true });
    writeFileSync(join(changeDir, '.spec-superflow.yaml'), 'state: exploring\nworkflow: full\nchange_name: test\n');
    return changeDir;
  }

  function runInject(args, cwd = tempDir) {
    try {
      const stdout = execFileSync(process.execPath, [CLI_PATH, 'inject', ...args], {
        cwd,
        encoding: 'utf-8',
        stdio: ['pipe', 'pipe', 'pipe'],
      });
      return { exitCode: 0, stdout: stdout.trim(), stderr: '' };
    } catch (err) {
      return {
        exitCode: err.status || 1,
        stdout: err.stdout?.toString().trim() || '',
        stderr: err.stderr?.toString().trim() || err.message,
      };
    }
  }

  it('requires explicit platforms instead of generating every supported platform', () => {
    const projectRoot = join(tempDir, 'no-default-platforms');
    mkdirSync(projectRoot, { recursive: true });
    const changeDir = makeChangeDir('no-default-platforms');

    const result = runInject([changeDir], projectRoot);

    assert.equal(result.exitCode, 2);
    assert.ok(result.stderr.includes('No platforms specified'));
    assert.equal(existsSync(join(projectRoot, '.cursor')), false);
    assert.equal(existsSync(join(projectRoot, '.github', 'copilot-instructions.md')), false);
    assert.equal(existsSync(join(projectRoot, 'GEMINI.md')), false);
  });

  it('rejects an empty platform list', () => {
    const projectRoot = join(tempDir, 'empty-platforms');
    mkdirSync(projectRoot, { recursive: true });
    const changeDir = makeChangeDir('empty-platforms');

    const result = runInject([changeDir, '--platforms', ','], projectRoot);

    assert.equal(result.exitCode, 2);
    assert.ok(result.stderr.includes('No valid platforms specified'));
  });

  it('writes only the explicitly requested platform', () => {
    const projectRoot = join(tempDir, 'explicit-claude');
    mkdirSync(projectRoot, { recursive: true });
    const changeDir = makeChangeDir('explicit-claude');

    const result = runInject([changeDir, '--platforms', 'claude'], projectRoot);

    assert.equal(result.exitCode, 0, result.stderr);
    assert.equal(existsSync(join(projectRoot, '.claude', 'always', 'phase-guard.md')), true);
    assert.equal(existsSync(join(projectRoot, '.cursor')), false);
    assert.equal(existsSync(join(projectRoot, '.github', 'copilot-instructions.md')), false);
    assert.equal(existsSync(join(projectRoot, 'GEMINI.md')), false);
  });
});
