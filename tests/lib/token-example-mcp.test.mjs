import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { join } from 'node:path';
import { describe, it } from 'node:test';

const SERVER = join(process.cwd(), 'servers', 'token-example-mcp.mjs');

function call(arguments_ = {}, token, url) {
  const request = {
    jsonrpc: '2.0',
    id: 1,
    method: 'tools/call',
    params: {
      name: 'spec_superflow_token_example_status',
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
  return {
    response,
    value: JSON.parse(response.result.content[0].text),
  };
}

describe('token example MCP', () => {
  it('reports a missing token without inventing a value', () => {
    const { value } = call();

    assert.deepEqual(value, {
      configured: false,
      urlConfigured: false,
      urlValid: false,
      urlLength: 0,
      tokenConfigured: false,
      tokenLength: 0,
      tokenFingerprint: null,
      source: 'plugin-bundled-stdio',
    });
  });

  it('receives an environment-provided token without returning the secret', () => {
    const token = 'local-example-token';
    const { response, value } = call({}, token, 'https://service.example/mcp');
    const serialized = JSON.stringify(response);

    assert.deepEqual(value, {
      configured: true,
      urlConfigured: true,
      urlValid: true,
      urlLength: 'https://service.example/mcp'.length,
      tokenConfigured: true,
      tokenLength: token.length,
      tokenFingerprint: createHash('sha256').update(token).digest('hex').slice(0, 12),
      source: 'plugin-bundled-stdio',
    });
    assert.equal(serialized.includes(token), false);
  });

  it('does not become configured with an invalid URL', () => {
    const { value } = call({}, 'configured-token', 'not-a-url');

    assert.equal(value.configured, false);
    assert.equal(value.urlConfigured, true);
    assert.equal(value.urlValid, false);
    assert.equal(value.tokenConfigured, true);
  });

  it('rejects arguments so callers cannot override credential sources', () => {
    const { response, value } = call({ token: 'override' }, 'configured-token');

    assert.equal(response.result.isError, true);
    assert.deepEqual(value, {
      configured: false,
      error: 'spec_superflow_token_example_status does not accept arguments',
    });
  });
});
