import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';

const ROOT = process.cwd();
const read = path => readFileSync(join(ROOT, path), 'utf8');

describe('VS Code Plugin documentation boundary', () => {
  it('documents one self-contained repository without external installation', () => {
    const productionMcp = JSON.parse(read('.mcp.json'));
    const english = read('docs/vscode-agent-plugin.md');
    const chinese = read('docs/vscode-agent-plugin-zh.md');

    assert.ok(productionMcp.mcpServers['spec-superflow']);
    assert.match(english, /bundled MCP bridge/);
    assert.match(chinese, /内置 MCP bridge/);
    assert.doesNotMatch(english, /npm install|offline package/i);
    assert.doesNotMatch(chinese, /npm install|离线包|全局 CLI|公司|内网/i);
  });
});
