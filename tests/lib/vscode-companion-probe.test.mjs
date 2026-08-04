import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, it } from 'node:test';

const ROOT = process.cwd();
const EXTENSION = join(ROOT, 'extensions', 'spec-superflow-companion');
const require = createRequire(import.meta.url);

function readJson(path) {
  return JSON.parse(readFileSync(path, 'utf8'));
}

describe('combined Spec Superflow VSIX', () => {
  it('contributes one Agent Plugin plus CLI bootstrap and Example MCP tools', () => {
    const rootPackage = readJson(join(ROOT, 'package.json'));
    const manifest = readJson(join(EXTENSION, 'package.json'));

    assert.equal(manifest.version, rootPackage.version);
    assert.equal(manifest.displayName, 'Spec Superflow');
    assert.deepEqual(manifest.contributes.chatPlugins, [{ path: './agent-plugin' }]);
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
      assert.throws(
        () => readFileSync(join(extensionRoot, 'agent-plugin', 'servers', 'token-example-mcp.mjs')),
        /ENOENT/,
      );
    } finally {
      rmSync(stagingRoot, { recursive: true, force: true });
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
