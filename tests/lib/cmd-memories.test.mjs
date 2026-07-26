import { afterEach, describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { spawnSync } from 'node:child_process';

const CLI = resolve('scripts/spec-superflow.mjs');
const tempDirs = [];

function makeProject() {
  const root = mkdtempSync(join(tmpdir(), 'ssf-memories-'));
  tempDirs.push(root);
  return root;
}

function topic({ name = 'runtime-market-selection', type = 'project', modified = '2026-07-23' } = {}) {
  return `---
name: ${name}
description: Runtime market mapping needed when requirements omit configuration details
type: ${type}
modified: ${modified}
---

# Runtime Markets

The ticket market field maps to the runtime configuration.

**Why:** The requirement does not repeat runtime configuration rules.

**How to apply:** Confirm the ticket field before selecting a configuration.

**Evidence:** Developer-confirmed runtime behavior on 2026-07-23.
`;
}

function addMemory(root) {
  const memoryDir = join(root, '.spec-superflow', 'memories');
  mkdirSync(memoryDir, { recursive: true });
  writeFileSync(
    join(memoryDir, 'MEMORY.md'),
    '# Project Memory\n\n- [Runtime markets](runtime-markets.md) - Read when selecting a runtime configuration.\n',
  );
  writeFileSync(join(memoryDir, 'runtime-markets.md'), topic());
  return memoryDir;
}

function runMemories(root, subcommand) {
  return spawnSync(process.execPath, [CLI, 'memories', subcommand, root], { encoding: 'utf-8' });
}

afterEach(() => {
  for (const dir of tempDirs.splice(0)) rmSync(dir, { recursive: true, force: true });
});

describe('ssf memories', () => {
  it('initializes only an empty MEMORY.md index', () => {
    const root = makeProject();
    const result = runMemories(root, 'init');
    const memoryDir = join(root, '.spec-superflow', 'memories');

    assert.equal(result.status, 0, result.stderr);
    assert.equal(readFileSync(join(memoryDir, 'MEMORY.md'), 'utf-8'), '# Project Memory\n');
    assert.equal(existsSync(join(memoryDir, 'core.md')), false);
    assert.equal(existsSync(join(memoryDir, 'memory_maintenance.md')), false);
  });

  it('does not overwrite an existing entrypoint', () => {
    const root = makeProject();
    const memoryDir = join(root, '.spec-superflow', 'memories');
    mkdirSync(memoryDir, { recursive: true });
    writeFileSync(join(memoryDir, 'MEMORY.md'), '# Existing\n');

    const result = runMemories(root, 'init');

    assert.equal(result.status, 0, result.stderr);
    assert.equal(readFileSync(join(memoryDir, 'MEMORY.md'), 'utf-8'), '# Existing\n');
  });

  it('refuses blind initialization over Serena-style memory', () => {
    const root = makeProject();
    const memoryDir = join(root, '.spec-superflow', 'memories');
    mkdirSync(memoryDir, { recursive: true });
    writeFileSync(join(memoryDir, 'core.md'), '# Legacy\n');

    const result = runMemories(root, 'init');

    assert.equal(result.status, 1);
    assert.match(result.stderr, /Serena-style or unindexed memory detected/);
  });

  it('lists the entrypoint and topic files without reading topic bodies', () => {
    const root = makeProject();
    addMemory(root);
    const result = runMemories(root, 'list');

    assert.equal(result.status, 0, result.stderr);
    assert.deepEqual(result.stdout.trim().split('\n'), ['MEMORY.md', 'runtime-markets.md']);
  });

  it('accepts a pure index and typed topic files', () => {
    const root = makeProject();
    addMemory(root);
    const result = runMemories(root, 'check');

    assert.equal(result.status, 0, result.stderr);
    assert.match(result.stdout, /typed topics indexed within load limits/);
  });

  it('rejects content stored directly in MEMORY.md', () => {
    const root = makeProject();
    const memoryDir = addMemory(root);
    writeFileSync(join(memoryDir, 'MEMORY.md'), '# Project Memory\n\n## Always Useful\n\n- Tests need a local service.\n');

    const result = runMemories(root, 'check');

    assert.equal(result.status, 1);
    assert.match(result.stderr, /must be a one-line topic link with a relevance hook/);
  });

  it('requires the exact entrypoint heading', () => {
    const root = makeProject();
    const memoryDir = join(root, '.spec-superflow', 'memories');
    mkdirSync(memoryDir, { recursive: true });
    writeFileSync(join(memoryDir, 'MEMORY.md'), '');

    const result = runMemories(root, 'check');

    assert.equal(result.status, 1);
    assert.match(result.stderr, /must start with '# Project Memory'/);
  });

  it('rejects duplicate topic links', () => {
    const root = makeProject();
    const memoryDir = addMemory(root);
    writeFileSync(
      join(memoryDir, 'MEMORY.md'),
      '# Project Memory\n\n- [Runtime markets](runtime-markets.md) - Read for runtime configuration.\n- [Markets](runtime-markets.md) - Read before selecting a market.\n',
    );

    const result = runMemories(root, 'check');

    assert.equal(result.status, 1);
    assert.match(result.stderr, /contains duplicate topic links/);
  });

  it('rejects broken and unsafe topic links', () => {
    const root = makeProject();
    const memoryDir = addMemory(root);
    writeFileSync(
      join(memoryDir, 'MEMORY.md'),
      '# Project Memory\n\n- [Missing](missing.md) - Read for missing context.\n- [Outside](../outside.md) - Read outside.\n',
    );

    const result = runMemories(root, 'check');

    assert.equal(result.status, 1);
    assert.match(result.stderr, /Broken topic link in MEMORY\.md: missing\.md/);
    assert.match(result.stderr, /Unsafe or invalid topic link in MEMORY\.md: \.\.\/outside\.md/);
  });

  it('rejects topic files that the index cannot discover', () => {
    const root = makeProject();
    const memoryDir = addMemory(root);
    writeFileSync(join(memoryDir, 'MEMORY.md'), '# Project Memory\n');

    const result = runMemories(root, 'check');

    assert.equal(result.status, 1);
    assert.match(result.stderr, /Topic file is not indexed by MEMORY\.md: runtime-markets\.md/);
  });

  it('requires typed frontmatter and rejects private user memory', () => {
    const root = makeProject();
    const memoryDir = addMemory(root);
    writeFileSync(join(memoryDir, 'runtime-markets.md'), '# Runtime Markets\n');
    let result = runMemories(root, 'check');
    assert.equal(result.status, 1);
    assert.match(result.stderr, /missing YAML frontmatter/);

    writeFileSync(join(memoryDir, 'runtime-markets.md'), topic({ type: 'user' }));
    result = runMemories(root, 'check');
    assert.equal(result.status, 1);
    assert.match(result.stderr, /unsupported memory type 'user'/);
  });

  it('requires a valid modified date and unique memory name', () => {
    const root = makeProject();
    const memoryDir = addMemory(root);
    writeFileSync(
      join(memoryDir, 'MEMORY.md'),
      '# Project Memory\n\n- [Runtime markets](runtime-markets.md) - Read for runtime configuration.\n- [Market reference](market-reference.md) - Read for the source ticket field.\n',
    );
    writeFileSync(join(memoryDir, 'runtime-markets.md'), topic({ modified: 'yesterday' }));
    writeFileSync(join(memoryDir, 'market-reference.md'), topic({ type: 'reference' }));

    const result = runMemories(root, 'check');

    assert.equal(result.status, 1);
    assert.match(result.stderr, /modified must be YYYY-MM-DD/);
    assert.match(result.stderr, /duplicate memory name 'runtime-market-selection'/);
  });

  it('enforces Claude-style entrypoint load limits', () => {
    const root = makeProject();
    const memoryDir = join(root, '.spec-superflow', 'memories');
    mkdirSync(memoryDir, { recursive: true });
    writeFileSync(join(memoryDir, 'MEMORY.md'), `${Array.from({ length: 201 }, (_, index) => `line ${index}`).join('\n')}\n`);

    const result = runMemories(root, 'check');

    assert.equal(result.status, 1);
    assert.match(result.stderr, /exceeds 200 lines/);
  });

  it('accepts an entrypoint at exactly 200 newline-terminated lines structurally only when entries are valid', () => {
    const root = makeProject();
    const memoryDir = join(root, '.spec-superflow', 'memories');
    mkdirSync(memoryDir, { recursive: true });
    const lines = ['# Project Memory', ...Array.from({ length: 199 }, () => '')];
    writeFileSync(join(memoryDir, 'MEMORY.md'), `${lines.join('\n')}\n`);

    const result = runMemories(root, 'check');

    assert.equal(result.status, 0, result.stderr);
  });

  it('enforces the 25,000-byte entrypoint limit', () => {
    const root = makeProject();
    const memoryDir = join(root, '.spec-superflow', 'memories');
    mkdirSync(memoryDir, { recursive: true });
    writeFileSync(join(memoryDir, 'MEMORY.md'), `# Project Memory\n\n${'x'.repeat(25_000)}\n`);

    const result = runMemories(root, 'check');

    assert.equal(result.status, 1);
    assert.match(result.stderr, /exceeds 25,000 bytes/);
  });
});
