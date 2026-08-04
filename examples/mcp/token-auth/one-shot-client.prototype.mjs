#!/usr/bin/env node

// PROTOTYPE: prove that a terminal-invoked client can call a stdio MCP once
// and cleanly exit without a long-running gateway.

import { spawn } from 'node:child_process';
import { randomBytes } from 'node:crypto';
import { once } from 'node:events';
import { dirname, resolve } from 'node:path';
import { createInterface } from 'node:readline';
import { fileURLToPath } from 'node:url';

const RUNS = 10;
const HERE = dirname(fileURLToPath(import.meta.url));
const SERVER = resolve(HERE, '../../../servers/token-example-mcp.mjs');
const TOOL = 'spec_superflow_token_example_status';
const ENV = {
  ...process.env,
  SPEC_SUPERFLOW_EXAMPLE_TOKEN:
    process.env.SPEC_SUPERFLOW_EXAMPLE_TOKEN || randomBytes(18).toString('hex'),
  SPEC_SUPERFLOW_EXAMPLE_URL:
    process.env.SPEC_SUPERFLOW_EXAMPLE_URL || 'https://service.example/mcp',
};

async function callOnce(run) {
  const startedAt = performance.now();
  const child = spawn(process.execPath, [SERVER], {
    env: ENV,
    stdio: ['pipe', 'pipe', 'pipe'],
  });
  const lines = createInterface({ input: child.stdout })[Symbol.asyncIterator]();
  const timeout = setTimeout(() => child.kill(), 5_000);
  let nextId = 0;
  let stderr = '';
  child.stderr.setEncoding('utf8');
  child.stderr.on('data', chunk => {
    stderr += chunk;
  });

  async function request(method, params = {}) {
    const id = ++nextId;
    child.stdin.write(`${JSON.stringify({ jsonrpc: '2.0', id, method, params })}\n`);
    const { value: line, done } = await lines.next();
    if (done) throw new Error(`${method} received no response${stderr ? `: ${stderr.trim()}` : ''}`);
    const message = JSON.parse(line);
    if (message.id !== id) throw new Error(`${method} received response id ${message.id}, expected ${id}`);
    if (message.error) throw new Error(message.error.message);
    return message.result;
  }

  try {
    const initialized = await request('initialize', {
      protocolVersion: '2025-06-18',
      capabilities: {},
      clientInfo: { name: 'spec-superflow-one-shot-prototype', version: '0.1.0' },
    });
    child.stdin.write(
      `${JSON.stringify({ jsonrpc: '2.0', method: 'notifications/initialized', params: {} })}\n`,
    );

    const listed = await request('tools/list');
    if (!listed.tools?.some(tool => tool.name === TOOL)) {
      throw new Error(`${TOOL} was not returned by tools/list`);
    }

    const called = await request('tools/call', { name: TOOL, arguments: {} });
    const text = called.content?.find(item => item.type === 'text')?.text;
    const result = JSON.parse(text);

    child.stdin.end();
    const [code, signal] = await once(child, 'close');
    if (code !== 0) throw new Error(`MCP server exited with code ${code} (${signal ?? 'no signal'})`);

    return {
      run,
      serverName: initialized.serverInfo?.name,
      tool: TOOL,
      configured: result.configured,
      tokenLength: result.tokenLength,
      tokenFingerprint: result.tokenFingerprint,
      exitCode: code,
      processExited: true,
      elapsedMs: Math.round(performance.now() - startedAt),
    };
  } finally {
    clearTimeout(timeout);
    if (child.exitCode === null && child.signalCode === null) child.kill();
  }
}

const results = [];
for (let run = 1; run <= RUNS; run += 1) {
  const result = await callOnce(run);
  results.push(result);
  process.stdout.write(`${JSON.stringify({ event: 'run-complete', ...result })}\n`);
}

const elapsed = results.map(result => result.elapsedMs);
process.stdout.write(
  `${JSON.stringify({
    event: 'prototype-summary',
    question: 'Can a Skill call a stdio MCP reliably without a long-running gateway?',
    successfulRuns: results.length,
    requestedRuns: RUNS,
    averageElapsedMs: Math.round(elapsed.reduce((sum, value) => sum + value, 0) / elapsed.length),
    maximumElapsedMs: Math.max(...elapsed),
    allProcessesExited: results.every(result => result.processExited),
  })}\n`,
);
