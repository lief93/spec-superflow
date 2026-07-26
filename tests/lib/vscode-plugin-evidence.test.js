import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';

const ROOT = process.cwd();
const read = (path) => readFileSync(join(ROOT, path), 'utf8');

describe('VS Code Plugin evidence boundary', () => {
  it('reports the production MCP as not configured', () => {
    const productionMcp = JSON.parse(read('.mcp.json'));
    const english = read('docs/vscode-agent-plugin.md');
    const chinese = read('docs/vscode-agent-plugin-zh.md');
    const evidence = read('validation/evidence/offline-install-upgrade.md');

    assert.deepEqual(productionMcp, { mcpServers: {} });
    assert.match(english, /Not Configured/);
    assert.match(chinese, /Not Configured/);
    assert.match(evidence, /Production Plugin MCP.*Not Configured/);
    assert.doesNotMatch(english, /Plugin-bundled test MCP starts[\s\S]*exposes its tool/);
    assert.doesNotMatch(chinese, /测试 MCP 能[\s\S]*被 Chat 调用/);
  });
});
