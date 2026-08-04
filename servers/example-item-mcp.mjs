#!/usr/bin/env node

import { createInterface } from 'node:readline';

const TOOL = {
  name: 'spec_superflow_example_read_item',
  description: 'Read one example item. Replace this server/tool mapping with the company Jira MCP mapping.',
  inputSchema: {
    type: 'object',
    required: ['item'],
    properties: {
      item: {
        type: 'string',
        description: 'Example item URL or key.',
      },
    },
    additionalProperties: false,
  },
  annotations: {
    readOnlyHint: true,
    destructiveHint: false,
    idempotentHint: true,
    openWorldHint: false,
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

function textResult(value, isError = false) {
  return {
    content: [{ type: 'text', text: JSON.stringify(value) }],
    ...(isError ? { isError: true } : {}),
  };
}

function readExampleItem(arguments_, env = process.env) {
  const item = typeof arguments_?.item === 'string' ? arguments_.item.trim() : '';
  const url = env.SPEC_SUPERFLOW_EXAMPLE_URL?.trim() ?? '';
  const token = env.SPEC_SUPERFLOW_EXAMPLE_TOKEN?.trim() ?? '';
  let endpointValid = false;
  try {
    endpointValid = ['http:', 'https:'].includes(new URL(url).protocol);
  } catch {
    // Missing or invalid example endpoint.
  }

  if (!item || item.length > 512 || Object.keys(arguments_ ?? {}).some(key => key !== 'item')) {
    return textResult({
      status: 'blocked',
      reason: 'invalid-example-item',
    }, true);
  }
  if (!endpointValid || !token) {
    return textResult({
      status: 'blocked',
      reason: 'example-mcp-not-configured',
      endpointConfigured: Boolean(url),
      credentialConfigured: Boolean(token),
    }, true);
  }

  return textResult({
    status: 'ready',
    item: {
      key: item,
      title: `Example item ${item}`,
      description: 'Replace this deterministic response with the company Jira MCP result.',
    },
    source: 'plugin-bundled-one-shot-stdio',
  });
}

function handle(message) {
  if (!message || message.jsonrpc !== '2.0') return;
  if (message.method === 'initialize') {
    result(message.id, {
      protocolVersion: message.params?.protocolVersion ?? '2025-06-18',
      capabilities: { tools: { listChanged: false } },
      serverInfo: { name: 'spec-superflow-example-item', version: '1.0.0' },
    });
    return;
  }
  if (message.method === 'ping') {
    result(message.id, {});
    return;
  }
  if (message.method === 'tools/list') {
    result(message.id, { tools: [TOOL] });
    return;
  }
  if (message.method === 'tools/call') {
    if (message.params?.name === TOOL.name) {
      result(message.id, readExampleItem(message.params?.arguments ?? {}));
    } else {
      error(message.id, -32602, `Unknown tool: ${message.params?.name ?? '<missing>'}`);
    }
    return;
  }
  if (message.id !== undefined) error(message.id, -32601, `Method not found: ${message.method}`);
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

export { readExampleItem };
