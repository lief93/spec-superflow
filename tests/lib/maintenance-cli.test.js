import { spawnSync } from 'node:child_process';
import {
  copyFileSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { afterEach, describe, it } from 'node:test';
import assert from 'node:assert/strict';

const ROOT = process.cwd();
const CLI = join(ROOT, 'scripts', 'spec-superflow.mjs');
const VERSION_MODULE = join(ROOT, 'scripts', 'lib', 'cmd-version.mjs');
const CONSISTENCY_SCRIPT = join(ROOT, 'scripts', 'check-version-consistency.mjs');
const tempRoots = [];

function tempRoot(prefix) {
  const root = mkdtempSync(join(tmpdir(), prefix));
  tempRoots.push(root);
  return root;
}

function write(path, content) {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, content);
}

function json(path, content) {
  write(path, `${JSON.stringify(content, null, 2)}\n`);
}

function workflowInit(version) {
  return `<!-- spec-superflow-plugin-version: ${version} -->
The bundled Plugin runtime must report version \`${version}\`.
`;
}

function agent(version) {
  return `---
name: Spec Superflow
---
<!-- spec-superflow-plugin-version: ${version} -->
`;
}

function createVersionFixture(root, version) {
  json(join(root, 'package.json'), { version });
  json(join(root, 'plugin.json'), { version });
  json(join(root, '.plugin/plugin.json'), { version });
  json(join(root, '.claude-plugin/plugin.json'), { version });
  json(join(root, '.claude-plugin/marketplace.json'), { plugins: [{ version }] });
  json(join(root, '.cursor-plugin/plugin.json'), { version });
  json(join(root, '.cursor-plugin/marketplace.json'), { metadata: { version } });
  json(join(root, '.codex-plugin/plugin.json'), { version });
  json(join(root, 'gemini-extension.json'), { version });
  json(join(root, '.github/plugin/marketplace.json'), {
    metadata: { version },
    plugins: [{ version }],
  });
  write(join(root, 'README.md'), `当前版本：\`v${version}\`\n`);
  write(join(root, 'INSTALL.md'), `当前发布版本：**v${version}**\n`);
  write(join(root, 'docs/README_en.md'), `Current: \`v${version}\`\n`);
  write(join(root, 'hooks/session-start'), `# v${version}: conditional injection\n`);
  write(join(root, 'llms.txt'), `Current version: v${version}.\n`);
  write(join(root, '.claude/always/phase-guard.md'), `# spec-superflow v${version} | guard\n`);
  write(join(root, 'GEMINI.md'), `# spec-superflow v${version} | guard\n`);
  write(join(root, 'commands/workflow-init.md'), workflowInit(version));
  write(join(root, 'agents/spec-superflow.agent.md'), agent(version));
}

afterEach(() => {
  for (const root of tempRoots.splice(0)) {
    rmSync(root, { recursive: true, force: true });
  }
});

describe('maintenance CLI behavior', () => {
  it('doctor exits non-zero outside a source checkout', () => {
    const root = tempRoot('ssf-doctor-process-');
    const result = spawnSync(process.execPath, [CLI, 'doctor'], {
      cwd: root,
      encoding: 'utf8',
    });

    assert.notEqual(result.status, 0, result.stdout);
    assert.match(result.stdout, /Some checks need attention/);
  });

  it('updates every bundled Plugin version reference from 0.14.0 to 0.15.0', () => {
    const root = tempRoot('ssf-version-sync-');
    createVersionFixture(root, '0.14.0');
    const runner = `import(${JSON.stringify(`file://${VERSION_MODULE}`)}).then(m => m.run(['0.15.0']))`;
    const result = spawnSync(process.execPath, ['--input-type=module', '--eval', runner], {
      cwd: root,
      encoding: 'utf8',
    });

    assert.equal(result.status, 0, result.stderr);
    const command = readFileSync(join(root, 'commands/workflow-init.md'), 'utf8');
    assert.doesNotMatch(command, /0\.14\.0/);
    assert.match(command, /spec-superflow-plugin-version: 0\.15\.0/);
    assert.match(command, /version `0\.15\.0`/);
    const agentSource = readFileSync(join(root, 'agents/spec-superflow.agent.md'), 'utf8');
    assert.doesNotMatch(agentSource, /0\.14\.0/);
    assert.match(agentSource, /spec-superflow-plugin-version: 0\.15\.0/);
  });

  it('consistency check rejects a stale workflow-init Plugin version', () => {
    const root = tempRoot('ssf-version-consistency-');
    createVersionFixture(root, '0.15.0');
    write(join(root, 'commands/workflow-init.md'), workflowInit('0.14.0'));
    const copiedScript = join(root, 'scripts/check-version-consistency.mjs');
    mkdirSync(dirname(copiedScript), { recursive: true });
    copyFileSync(CONSISTENCY_SCRIPT, copiedScript);

    const result = spawnSync(process.execPath, [copiedScript], {
      cwd: root,
      encoding: 'utf8',
    });

    assert.equal(result.status, 1, result.stdout);
    assert.match(result.stdout, /commands\/workflow-init\.md/);
    assert.match(result.stdout, /found:\s+0\.14\.0/);
  });

  it('consistency check rejects a stale Agent Plugin version', () => {
    const root = tempRoot('ssf-agent-version-consistency-');
    createVersionFixture(root, '0.15.0');
    write(join(root, 'agents/spec-superflow.agent.md'), agent('0.14.0'));
    const copiedScript = join(root, 'scripts/check-version-consistency.mjs');
    mkdirSync(dirname(copiedScript), { recursive: true });
    copyFileSync(CONSISTENCY_SCRIPT, copiedScript);

    const result = spawnSync(process.execPath, [copiedScript], {
      cwd: root,
      encoding: 'utf8',
    });

    assert.equal(result.status, 1, result.stdout);
    assert.match(result.stdout, /agents\/spec-superflow\.agent\.md/);
    assert.match(result.stdout, /found:\s+0\.14\.0/);
  });

});
