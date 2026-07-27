#!/usr/bin/env node

import { createHash } from 'node:crypto';
import { createInterface } from 'node:readline';

const TOOL = {
  name: 'spec_superflow_token_example_status',
  description: 'Verify that a user-provided token reached a Plugin-bundled stdio MCP without revealing it.',
  inputSchema: {
    type: 'object',
    properties: {},
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
    content: [{ type: 'text', text: JSON.stringify(value, null, 2) }],
    ...(isError ? { isError: true } : {}),
  };
}

function tokenStatus(arguments_) {
  if (Object.keys(arguments_ ?? {}).length > 0) {
    return textResult(
      {
        configured: false,
        error: 'spec_superflow_token_example_status does not accept arguments',
      },
      true,
    );
  }

  const token = process.env.SPEC_SUPERFLOW_EXAMPLE_TOKEN?.trim() ?? '';
  const url = process.env.SPEC_SUPERFLOW_EXAMPLE_URL?.trim() ?? '';
  let urlValid = false;
  try {
    const parsed = new URL(url);
    urlValid = ['http:', 'https:'].includes(parsed.protocol);
  } catch {
    // Invalid or missing URL.
  }
  return textResult({
    configured: token.length > 0 && urlValid,
    urlConfigured: url.length > 0,
    urlValid,
    urlLength: url.length,
    tokenConfigured: token.length > 0,
    tokenLength: token.length,
    tokenFingerprint: token
      ? createHash('sha256').update(token).digest('hex').slice(0, 12)
      : null,
    source: 'plugin-bundled-stdio',
  });
}

function handle(message) {
  if (!message || message.jsonrpc !== '2.0') return;

  if (message.method === 'initialize') {
    result(message.id, {
      protocolVersion: message.params?.protocolVersion ?? '2025-06-18',
      capabilities: { tools: { listChanged: false } },
      serverInfo: {
        name: 'spec-superflow-token-example',
        version: '1.0.0',
      },
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
      result(message.id, tokenStatus(message.params?.arguments ?? {}));
    } else {
      error(message.id, -32602, `Unknown tool: ${message.params?.name ?? '<missing>'}`);
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

export { tokenStatus };
