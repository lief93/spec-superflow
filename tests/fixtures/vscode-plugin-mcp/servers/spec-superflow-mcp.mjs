#!/usr/bin/env node

import { dirname } from 'node:path';
import { createInterface } from 'node:readline';
import { fileURLToPath } from 'node:url';

const SERVER_DIR = dirname(fileURLToPath(import.meta.url));
const PLUGIN_ROOT = dirname(SERVER_DIR);

const HEALTH_TOOL = {
  name: 'spec_superflow_plugin_health',
  description: 'Report whether the test MCP server bundled with the plugin is running.',
  inputSchema: {
    type: 'object',
    properties: {},
    additionalProperties: false,
  },
};

function write(message) {
  process.stdout.write(`${JSON.stringify(message)}\n`);
}

function result(id, value) {
  write({ jsonrpc: '2.0', id, result: value });
}

function error(id, code, message) {
  write({ jsonrpc: '2.0', id, error: { code, message } });
}

function handle(message) {
  if (!message || message.jsonrpc !== '2.0') {
    return;
  }

  if (message.method === 'initialize') {
    result(message.id, {
      protocolVersion: message.params?.protocolVersion ?? '2025-06-18',
      capabilities: {
        tools: {
          listChanged: false,
        },
      },
      serverInfo: {
        name: 'spec-superflow-local',
        version: '0.0.0',
      },
    });
    return;
  }

  if (message.method === 'ping') {
    result(message.id, {});
    return;
  }

  if (message.method === 'tools/list') {
    result(message.id, { tools: [HEALTH_TOOL] });
    return;
  }

  if (message.method === 'tools/call') {
    if (message.params?.name !== HEALTH_TOOL.name) {
      error(message.id, -32602, `Unknown tool: ${message.params?.name ?? '<missing>'}`);
      return;
    }

    result(message.id, {
      content: [
        {
          type: 'text',
          text: JSON.stringify({
            status: 'ok',
            transport: 'stdio',
            pluginRoot: PLUGIN_ROOT,
            workingDirectory: process.cwd(),
          }),
        },
      ],
    });
    return;
  }

  if (message.id !== undefined) {
    error(message.id, -32601, `Method not found: ${message.method}`);
  }
}

const input = createInterface({
  input: process.stdin,
  crlfDelay: Infinity,
});

input.on('line', line => {
  if (!line.trim()) {
    return;
  }

  try {
    handle(JSON.parse(line));
  } catch (cause) {
    process.stderr.write(`Invalid MCP message: ${cause.message}\n`);
  }
});
