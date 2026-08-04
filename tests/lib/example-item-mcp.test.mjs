import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { join } from 'node:path';
import { describe, it } from 'node:test';

const SERVER = join(process.cwd(), 'servers', 'example-item-mcp.mjs');

function call(arguments_, token = '', url = '') {
  const request = {
    jsonrpc: '2.0',
    id: 1,
    method: 'tools/call',
    params: {
      name: 'spec_superflow_example_read_item',
      arguments: arguments_,
    },
  };
  const result = spawnSync(process.execPath, [SERVER], {
    env: {
      ...process.env,
      SPEC_SUPERFLOW_EXAMPLE_TOKEN: token,
      SPEC_SUPERFLOW_EXAMPLE_URL: url,
    },
    input: `${JSON.stringify(request)}\n`,
    encoding: 'utf8',
  });
  assert.equal(result.status, 0, result.stderr);
  const response = JSON.parse(result.stdout.trim());
  return { response, value: JSON.parse(response.result.content[0].text) };
}

describe('replaceable Example MCP server', () => {
  it('reads one item without returning its endpoint or token', () => {
    const token = 'company-example-only-secret';
    const url = 'https://example.invalid/mcp';
    const { response, value } = call({ item: 'MOBILE-123' }, token, url);
    const serialized = JSON.stringify(response);

    assert.deepEqual(value, {
      status: 'ready',
      item: {
        key: 'MOBILE-123',
        title: 'Example item MOBILE-123',
        description: 'Replace this deterministic response with the company Jira MCP result.',
      },
      source: 'plugin-bundled-one-shot-stdio',
    });
    assert.equal(serialized.includes(token), false);
    assert.equal(serialized.includes(url), false);
  });

  it('fails closed when credentials are unavailable', () => {
    const { response, value } = call({ item: 'MOBILE-123' });

    assert.equal(response.result.isError, true);
    assert.deepEqual(value, {
      status: 'blocked',
      reason: 'example-mcp-not-configured',
      endpointConfigured: false,
      credentialConfigured: false,
    });
  });

  it('rejects missing and extra item arguments', () => {
    for (const arguments_ of [{}, { item: 'MOBILE-123', tool: 'override' }]) {
      const { response, value } = call(
        arguments_,
        'company-example-only-secret',
        'https://example.invalid/mcp',
      );
      assert.equal(response.result.isError, true);
      assert.deepEqual(value, { status: 'blocked', reason: 'invalid-example-item' });
    }
  });
});
