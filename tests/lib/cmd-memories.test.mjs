import { afterEach, describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { spawnSync } from 'node:child_process';

const CLI = resolve('scripts/spec-superflow.mjs');
const tempDirs = [];

function makeProject() {
  const root = mkdtempSync(join(tmpdir(), 'ssf-memories-'));
  tempDirs.push(root);
  mkdirSync(join(root, '.spec-superflow', 'memories', 'feature'), { recursive: true });
  writeFileSync(join(root, '.spec-superflow', 'memories', 'memory_maintenance.md'), '# Policy\n\nExample `mem:missing-example`.\n');
  writeFileSync(join(root, '.spec-superflow', 'memories', 'core.md'), '# Core\n\n- Feature rules: `mem:feature/core`.\n');
  writeFileSync(join(root, '.spec-superflow', 'memories', 'feature', 'core.md'), '# Feature\n\n- Stable rule.\n');
  return root;
}

function runMemories(root, subcommand) {
  return spawnSync(process.execPath, [CLI, 'memories', subcommand, root], { encoding: 'utf-8' });
}

afterEach(() => {
  for (const dir of tempDirs.splice(0)) rmSync(dir, { recursive: true, force: true });
});

describe('ssf memories', () => {
  it('lists nested memories by logical name', () => {
    const result = runMemories(makeProject(), 'list');

    assert.equal(result.status, 0, result.stderr);
    assert.deepEqual(result.stdout.trim().split('\n'), ['core', 'feature/core', 'memory_maintenance']);
  });

  it('checks marked references and ignores policy examples', () => {
    const result = runMemories(makeProject(), 'check');

    assert.equal(result.status, 0, result.stderr);
    assert.match(result.stdout, /no broken references/);
  });

  it('fails when a project memory references a missing target', () => {
    const root = makeProject();
    writeFileSync(join(root, '.spec-superflow', 'memories', 'feature', 'core.md'), '# Feature\n\n- More: `mem:feature/missing`.\n');

    const result = runMemories(root, 'check');

    assert.equal(result.status, 1);
    assert.match(result.stderr, /Broken reference in feature\/core: mem:feature\/missing/);
  });
});
