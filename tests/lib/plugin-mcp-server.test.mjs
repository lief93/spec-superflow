import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';
import { join } from 'node:path';
import { describe, it } from 'node:test';

const ROOT = join(process.cwd(), 'tests', 'fixtures', 'vscode-plugin-mcp');

function startClient() {
  const process = spawn(
    globalThis.process.execPath,
    ['servers/spec-superflow-mcp.mjs'],
    {
      cwd: ROOT,
      stdio: ['pipe', 'pipe', 'pipe'],
    },
  );
  const pending = new Map();
  const output = createInterface({
    input: process.stdout,
    crlfDelay: Infinity,
  });

  output.on('line', line => {
    const message = JSON.parse(line);
    const request = pending.get(message.id);
    if (request) {
      pending.delete(message.id);
      request(message);
    }
  });

  return {
    request(id, method, params = {}) {
      return new Promise(resolve => {
        pending.set(id, resolve);
        process.stdin.write(`${JSON.stringify({
          jsonrpc: '2.0',
          id,
          method,
          params,
        })}\n`);
      });
    },
    notify(method, params = {}) {
      process.stdin.write(`${JSON.stringify({
        jsonrpc: '2.0',
        method,
        params,
      })}\n`);
    },
    close() {
      output.close();
      process.kill();
    },
  };
}

describe('plugin MCP server', () => {
  it('initializes, lists its tool, and handles a tool call', async () => {
    const client = startClient();

    try {
      const initialized = await client.request(1, 'initialize', {
        protocolVersion: '2025-06-18',
        capabilities: {},
        clientInfo: {
          name: 'spec-superflow-test',
          version: '1.0.0',
        },
      });
      assert.equal(initialized.result.serverInfo.name, 'spec-superflow-local');
      assert.equal(initialized.result.protocolVersion, '2025-06-18');

      client.notify('notifications/initialized');

      const tools = await client.request(2, 'tools/list');
      assert.deepEqual(
        tools.result.tools.map(tool => tool.name),
        ['spec_superflow_plugin_health'],
      );

      const called = await client.request(3, 'tools/call', {
        name: 'spec_superflow_plugin_health',
        arguments: {},
      });
      const health = JSON.parse(called.result.content[0].text);

      assert.equal(health.status, 'ok');
      assert.equal(health.transport, 'stdio');
      assert.equal(health.pluginRoot, ROOT);
      assert.equal(health.workingDirectory, ROOT);
    } finally {
      client.close();
    }
  });
});
