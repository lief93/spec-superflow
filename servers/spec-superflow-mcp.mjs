#!/usr/bin/env node

import { spawnSync } from 'node:child_process';
import { existsSync, readFileSync, statSync } from 'node:fs';
import { dirname, isAbsolute, join } from 'node:path';
import { createInterface } from 'node:readline';
import { fileURLToPath } from 'node:url';

const SERVER_DIR = dirname(fileURLToPath(import.meta.url));
const PLUGIN_ROOT = dirname(SERVER_DIR);
const CLI = join(PLUGIN_ROOT, 'scripts', 'spec-superflow.mjs');
const PACKAGE = JSON.parse(readFileSync(join(PLUGIN_ROOT, 'package.json'), 'utf8'));
const ALLOWED_COMMANDS = new Set([
  '--version',
  'audit',
  'check-update',
  'config',
  'guard',
  'infer-workflow',
  'memories',
  'project',
  'review-package',
  'state',
  'sync',
  'task-brief',
  'validate',
]);

const TOOLS = [
  {
    name: 'spec_superflow_health',
    description: 'Verify the Spec Superflow runtime bundled in this Plugin.',
    inputSchema: {
      type: 'object',
      properties: {},
      additionalProperties: false,
    },
  },
  {
    name: 'spec_superflow_run',
    description: 'Run a bundled Spec Superflow command in the selected workspace.',
    inputSchema: {
      type: 'object',
      properties: {
        workspace: {
          type: 'string',
          description: 'Absolute path to the target repository.',
        },
        args: {
          type: 'array',
          minItems: 1,
          items: { type: 'string' },
          description: 'Arguments after the logical ssf command.',
        },
      },
      required: ['workspace', 'args'],
      additionalProperties: false,
    },
  },
];

function write(message) {
  process.stdout.write(`${JSON.stringify(message)}\n`);
}

function result(id, value) {
  write({ jsonrpc: '2.0', id, result: value });
}

function error(id, code, message) {
  write({ jsonrpc: '2.0', id, error: { code, message } });
}

function textResult(value, isError = false) {
  return {
    content: [{ type: 'text', text: JSON.stringify(value, null, 2) }],
    ...(isError ? { isError: true } : {}),
  };
}

function health() {
  return {
    status: existsSync(CLI) ? 'ready' : 'blocked',
    runtime: 'bundled',
    version: PACKAGE.version,
    node: process.version,
    transport: 'stdio',
    pluginRoot: PLUGIN_ROOT,
    workingDirectory: process.cwd(),
  };
}

function runBundled({ workspace, args }) {
  if (!isAbsolute(workspace) || !existsSync(workspace) || !statSync(workspace).isDirectory()) {
    throw new Error('workspace must be an existing absolute directory');
  }
  if (!Array.isArray(args) || args.length === 0 || !args.every(arg => typeof arg === 'string')) {
    throw new Error('args must be a non-empty string array');
  }
  if (!ALLOWED_COMMANDS.has(args[0])) {
    throw new Error(`unsupported bundled command: ${args[0]}`);
  }

  if (args[0] === 'check-update') {
    return {
      exitCode: 2,
      stdout: 'Plugin updates are managed by the VS Code Agent Plugins view.',
      stderr: '',
      workspace,
    };
  }

  const execution = spawnSync(process.execPath, [CLI, ...args], {
    cwd: workspace,
    encoding: 'utf8',
    maxBuffer: 10 * 1024 * 1024,
  });
  if (execution.error) {
    throw execution.error;
  }

  return {
    exitCode: execution.status ?? 1,
    stdout: execution.stdout.trim(),
    stderr: execution.stderr.trim(),
    workspace,
  };
}

function handle(message) {
  if (!message || message.jsonrpc !== '2.0') return;

  if (message.method === 'initialize') {
    result(message.id, {
      protocolVersion: message.params?.protocolVersion ?? '2025-06-18',
      capabilities: { tools: { listChanged: false } },
      serverInfo: { name: 'spec-superflow-local', version: PACKAGE.version },
    });
    return;
  }
  if (message.method === 'ping') {
    result(message.id, {});
    return;
  }
  if (message.method === 'tools/list') {
    result(message.id, { tools: TOOLS });
    return;
  }
  if (message.method === 'tools/call') {
    try {
      const name = message.params?.name;
      const args = message.params?.arguments ?? {};
      if (name === 'spec_superflow_health') {
        result(message.id, textResult(health()));
      } else if (name === 'spec_superflow_run') {
        const execution = runBundled(args);
        result(message.id, textResult(execution, execution.exitCode > 2));
      } else {
        error(message.id, -32602, `Unknown tool: ${name ?? '<missing>'}`);
      }
    } catch (cause) {
      result(message.id, textResult({ error: cause.message }, true));
    }
    return;
  }
  if (message.id !== undefined) {
    error(message.id, -32601, `Method not found: ${message.method}`);
  }
}

const input = createInterface({ input: process.stdin, crlfDelay: Infinity });
input.on('line', line => {
  if (!line.trim()) return;
  try {
    handle(JSON.parse(line));
  } catch (cause) {
    process.stderr.write(`Invalid MCP message: ${cause.message}\n`);
  }
});
