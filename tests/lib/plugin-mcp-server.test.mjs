import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { existsSync, mkdtempSync, rmSync } from 'node:fs';
import { createInterface } from 'node:readline';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, it } from 'node:test';

const ROOT = process.cwd();

function startClient() {
  const child = spawn(process.execPath, ['servers/spec-superflow-mcp.mjs'], {
    cwd: ROOT,
    stdio: ['pipe', 'pipe', 'pipe'],
  });
  const pending = new Map();
  const output = createInterface({ input: child.stdout, crlfDelay: Infinity });

  output.on('line', line => {
    const message = JSON.parse(line);
    pending.get(message.id)?.(message);
    pending.delete(message.id);
  });

  return {
    request(id, method, params = {}) {
      return new Promise(resolve => {
        pending.set(id, resolve);
        child.stdin.write(`${JSON.stringify({ jsonrpc: '2.0', id, method, params })}\n`);
      });
    },
    notify(method, params = {}) {
      child.stdin.write(`${JSON.stringify({ jsonrpc: '2.0', method, params })}\n`);
    },
    close() {
      output.close();
      child.kill();
    },
  };
}

describe('production Plugin MCP bridge', () => {
  it('reports bundled health and executes the bundled CLI in a target workspace', async () => {
    const client = startClient();

    try {
      const initialized = await client.request(1, 'initialize', {
        protocolVersion: '2025-06-18',
        capabilities: {},
        clientInfo: { name: 'spec-superflow-test', version: '1.0.0' },
      });
      assert.equal(initialized.result.serverInfo.name, 'spec-superflow-local');

      client.notify('notifications/initialized');

      const tools = await client.request(2, 'tools/list');
      assert.deepEqual(
        tools.result.tools.map(tool => tool.name),
        ['spec_superflow_health', 'spec_superflow_run'],
      );

      const healthCall = await client.request(3, 'tools/call', {
        name: 'spec_superflow_health',
        arguments: {},
      });
      const health = JSON.parse(healthCall.result.content[0].text);
      assert.equal(health.status, 'ready');
      assert.equal(health.runtime, 'bundled');
      assert.equal(health.pluginRoot, ROOT);

      const workspace = mkdtempSync(join(tmpdir(), 'ssf-plugin-workspace-'));
      try {
        const versionCall = await client.request(4, 'tools/call', {
          name: 'spec_superflow_run',
          arguments: { workspace, args: ['--version'] },
        });
        const execution = JSON.parse(versionCall.result.content[0].text);
        assert.equal(execution.exitCode, 0);
        assert.equal(execution.stdout, '0.14.0');
        assert.equal(execution.workspace, workspace);

        const memoryCall = await client.request(5, 'tools/call', {
          name: 'spec_superflow_run',
          arguments: { workspace, args: ['memories', 'init'] },
        });
        const memoryExecution = JSON.parse(memoryCall.result.content[0].text);
        assert.equal(memoryExecution.exitCode, 0);
        assert.equal(
          existsSync(join(workspace, '.spec-superflow', 'memories', 'MEMORY.md')),
          true,
        );
      } finally {
        rmSync(workspace, { recursive: true, force: true });
      }
    } finally {
      client.close();
    }
  });
});
