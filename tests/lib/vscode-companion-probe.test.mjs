import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { createRequire } from 'node:module';
import { mkdtempSync, readFileSync, readdirSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, relative } from 'node:path';
import { describe, it } from 'node:test';

const ROOT = process.cwd();
const EXTENSION = join(ROOT, 'extensions', 'spec-superflow-companion');
const require = createRequire(import.meta.url);

function readJson(path) {
  return JSON.parse(readFileSync(path, 'utf8'));
}

function sha256(path) {
  return createHash('sha256').update(readFileSync(path)).digest('hex');
}

function stageManifest(root, current = root) {
  return readdirSync(current, { withFileTypes: true })
    .sort((a, b) => a.name.localeCompare(b.name))
    .flatMap(entry => {
      const path = join(current, entry.name);
      if (entry.isDirectory()) return stageManifest(root, path);
      const name = relative(root, path).split('\\').join('/');
      return [{ path: name, sha256: sha256(path) }];
    });
}

describe('combined Spec Superflow VSIX', () => {
  it('contributes exactly two Agent Plugins plus unchanged CLI bootstrap and Example MCP tools', () => {
    const rootPackage = readJson(join(ROOT, 'package.json'));
    const manifest = readJson(join(EXTENSION, 'package.json'));

    assert.equal(manifest.version, rootPackage.version);
    assert.equal(manifest.displayName, 'Spec Superflow');
    assert.deepEqual(manifest.contributes.chatPlugins, [
      { path: './agent-plugin' },
      { path: './matt-plugin' },
    ]);
    assert.deepEqual(
      manifest.contributes.languageModelTools.map(tool => tool.name),
      [
        'spec_superflow_cli_status',
        'spec_superflow_install_cli',
        'spec_superflow_example_mcp_read',
      ],
    );
    assert.deepEqual(manifest.dependencies, undefined);
  });

  it('stages a self-contained Agent Plugin without a native MCP dependency', () => {
    const stagingRoot = mkdtempSync(join(tmpdir(), 'spec-superflow-vsix-stage-test-'));
    try {
      const built = spawnSync(
        process.execPath,
        [join(ROOT, 'scripts', 'build-vscode-vsix.mjs'), '--stage-only', stagingRoot],
        { cwd: ROOT, encoding: 'utf8' },
      );
      assert.equal(built.status, 0, built.stderr || built.stdout);

      const extensionRoot = join(stagingRoot, 'extension');
      const plugin = readJson(join(extensionRoot, 'agent-plugin', 'plugin.json'));
      const command = readFileSync(
        join(extensionRoot, 'agent-plugin', 'commands', 'workflow-init.md'),
        'utf8',
      );
      const setupAgent = readFileSync(
        join(extensionRoot, 'agent-plugin', 'agents', 'spec-superflow-setup.agent.md'),
        'utf8',
      );
      const exampleSkill = readFileSync(
        join(extensionRoot, 'agent-plugin', 'skills', 'example-mcp-reader', 'SKILL.md'),
        'utf8',
      );
      const mattPlugin = readJson(join(extensionRoot, 'matt-plugin', 'plugin.json'));
      const mattProvenance = readJson(join(extensionRoot, 'matt-plugin', 'provenance.json'));

      assert.equal(plugin.mcpServers, undefined);
      assert.equal(
        readFileSync(join(extensionRoot, 'agent-plugin', 'servers', 'example-item-mcp.mjs'), 'utf8')
          .includes('spec_superflow_example_read_item'),
        true,
      );
      assert.equal(readFileSync(join(extensionRoot, 'agent-plugin', 'package.json'), 'utf8').includes('0.15.0'), true);
      assert.match(command, /spec_superflow_cli_status/);
      assert.match(command, /spec_superflow_install_cli/);
      assert.doesNotMatch(command, /optional_mcp|token_example|MCP: List Servers/i);
      assert.match(setupAgent, /spec_superflow_cli_status/);
      assert.match(exampleSkill, /spec_superflow_example_mcp_read/);
      assert.doesNotMatch(exampleSkill, /JSON-RPC|child_process|server path|token argument/i);
      assert.equal(mattPlugin.name, 'matt-engineering');
      assert.equal(mattProvenance.selectedSkills.length, 22);
      assert.equal(mattProvenance.files.length, 66);
      assert.doesNotMatch(setupAgent, /Matt Engineering|ask-matt|diagnosing-bugs/);
      assert.throws(
        () => readFileSync(join(extensionRoot, 'agent-plugin', 'servers', 'token-example-mcp.mjs')),
        /ENOENT/,
      );
    } finally {
      rmSync(stagingRoot, { recursive: true, force: true });
    }
  });

  it('builds identical staged digests and VSIX bytes twice in npm offline mode', () => {
    const root = mkdtempSync(join(tmpdir(), 'spec-superflow-vsix-repeat-'));
    try {
      const outputs = [];
      const manifests = [];
      for (const run of ['one', 'two']) {
        const cache = join(root, `empty-cache-${run}`);
        const stage = join(root, `stage-${run}`);
        const output = join(root, `combined-${run}.vsix`);
        const env = {
          ...process.env,
          npm_config_cache: cache,
          npm_config_offline: 'true',
          npm_config_registry: 'http://127.0.0.1:9/unreachable',
        };
        const staged = spawnSync(
          process.execPath,
          [join(ROOT, 'scripts', 'build-vscode-vsix.mjs'), '--stage-only', stage],
          { cwd: ROOT, encoding: 'utf8', env },
        );
        assert.equal(staged.status, 0, staged.stderr || staged.stdout);
        manifests.push(stageManifest(stage));

        const built = spawnSync(
          process.execPath,
          [join(ROOT, 'scripts', 'build-vscode-vsix.mjs'), output],
          { cwd: ROOT, encoding: 'utf8', env },
        );
        assert.equal(built.status, 0, built.stderr || built.stdout);
        outputs.push(sha256(output));
      }

      assert.deepEqual(manifests[0], manifests[1]);
      assert.equal(outputs[0], outputs[1]);
      const builder = readFileSync(join(ROOT, 'scripts', 'build-vscode-vsix.mjs'), 'utf8');
      assert.doesNotMatch(builder, /spawnSync\(\s*['"]git['"]|\bfetch\s*\(|https?\.request|npm\s+(install|update)/i);
      assert.doesNotMatch(builder, /sync-matt-plugin/);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it('keeps the Example MCP behind a fixed one-shot wrapper contract', () => {
    const source = readFileSync(join(EXTENSION, 'extension.cjs'), 'utf8');
    const skill = readFileSync(
      join(EXTENSION, 'agent-plugin-additions', 'skills', 'example-mcp-reader', 'SKILL.md'),
      'utf8',
    );

    assert.match(source, /spec_superflow_example_mcp_read/);
    assert.match(source, /example-item-mcp\.mjs/);
    assert.match(source, /context\.secrets/);
    assert.doesNotMatch(source, /fetch\(|https?\.request|XMLHttpRequest|net\.|tls\./);
    assert.match(skill, /spec_superflow_example_mcp_read/);
    assert.match(skill, /item URL or key/i);
    assert.doesNotMatch(skill, /initialize|tools\/list|tools\/call|stdio|JSON-RPC/i);
  });

  it('runs the bundled Example MCP for one call and exits', async () => {
    const extension = require(join(EXTENSION, 'extension.cjs'));
    const token = 'one-shot-example-secret';
    const value = await extension.callOneShotMcp({
      launcher: join(ROOT, 'servers', 'spec-superflow-mcp-launcher.cmd'),
      server: join(ROOT, 'servers', 'example-item-mcp.mjs'),
      tool: 'spec_superflow_example_read_item',
      arguments_: { item: 'MOBILE-456' },
      env: {
        ...process.env,
        SPEC_SUPERFLOW_EXAMPLE_URL: 'https://example.invalid/mcp',
        SPEC_SUPERFLOW_EXAMPLE_TOKEN: token,
      },
    });

    assert.equal(value.status, 'ready');
    assert.equal(value.item.key, 'MOBILE-456');
    assert.equal(JSON.stringify(value).includes(token), false);
  });
});
