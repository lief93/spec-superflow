import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';

const ROOT = process.cwd();
const read = path => readFileSync(join(ROOT, path), 'utf8');

describe('VS Code Plugin documentation boundary', () => {
  it('documents CLI bootstrap and optional credentialed MCP setup', () => {
    const productionMcp = JSON.parse(read('.mcp.json'));
    const server = read('servers/spec-superflow-mcp.mjs');
    const english = read('docs/vscode-agent-plugin.md');
    const chinese = read('docs/vscode-agent-plugin-zh.md');

    assert.ok(productionMcp.mcpServers['spec-superflow']);
    for (const tool of [
      'spec_superflow_cli_status',
      'spec_superflow_install_cli',
      'spec_superflow_optional_mcp_status',
      'spec_superflow_install_optional_mcp',
    ]) {
      assert.match(server, new RegExp(tool));
      assert.match(english, new RegExp(tool));
      assert.match(chinese, new RegExp(tool));
    }
    assert.doesNotMatch(`${server}\n${english}\n${chinese}`, /spec_superflow_run/);
    assert.match(english, /business MCP is optional/i);
    assert.match(chinese, /业务 MCP 是可选能力/);
    assert.match(english, /workflow.*READY.*optionalMcp.*SKIPPED/is);
    assert.match(chinese, /workflow.*READY.*optionalMcp.*SKIPPED/is);
    assert.match(english, /keeps both values visible/i);
    assert.match(chinese, /两项输入都保持可见/);
    assert.match(english, /VS Code[\s\S]*secure credentials\s+store/i);
    assert.match(chinese, /VS Code[\s\S]*安全凭据存储/i);
    assert.match(english, /spec-superflow-mcp-launcher\.cmd/);
    assert.match(chinese, /spec-superflow-mcp-launcher\.cmd/);
  });

  it('documents workflow-init as the only install entry and local Plugin source ownership', () => {
    const english = read('docs/vscode-agent-plugin.md');
    const chinese = read('docs/vscode-agent-plugin-zh.md');

    assert.match(english, /type `\/workflow-init`/i);
    assert.match(
      english,
      /setup reports `workflow=READY`[\s\S]*select \*\*Spec Superflow\*\* and describe a\s+requirement/i,
    );
    assert.match(chinese, /输入 `\/workflow-init`/);
    assert.match(chinese, /返回 `workflow=READY`[\s\S]*选择 \*\*Spec Superflow\*\*[\s\S]*描述需求/);
    assert.match(
      english,
      /built-in \*\*Agent\*\*[\s\S]*type `\/workflow-init`[\s\S]*Click it or press \*\*Tab\*\*/i,
    );
    assert.match(english, /reports `workflow=READY`[\s\S]*select \*\*Spec Superflow\*\*/i);
    assert.match(
      chinese,
      /内置 \*\*Agent\*\*[\s\S]*输入 `\/workflow-init`[\s\S]*鼠标点击或按 \*\*Tab\*\*/,
    );
    assert.match(chinese, /返回 `workflow=READY`[\s\S]*选择 \*\*Spec Superflow\*\*/);
    assert.match(english, /Run `\/workflow-init` before starting a requirement/i);
    assert.match(chinese, /开始需求前先执行 `\/workflow-init`/);
    assert.doesNotMatch(english, /continues the original request once/);
    assert.doesNotMatch(chinese, /自动继续原需求一次/);
    assert.match(english, /current `\$\{PLUGIN_ROOT\}` only/);
    assert.match(chinese, /当前 `\$\{PLUGIN_ROOT\}`/);
    assert.match(english, /no second Spec repository or archive is required/i);
    assert.match(chinese, /不需要第二份 Spec/);
    assert.doesNotMatch(chinese, /公司|内网/);
  });

  it('documents direct CLI workflow execution and independent project instructions', () => {
    const english = read('docs/vscode-agent-plugin.md');
    const chinese = read('docs/vscode-agent-plugin-zh.md');

    assert.match(english, /Skills execute `ssf state`/);
    assert.match(chinese, /Skills 直接执行 `ssf state`/);
    assert.match(english, /\.github\/instructions\/spec-superflow\.instructions\.md/);
    assert.match(chinese, /\.github\/instructions\/spec-superflow\.instructions\.md/);
    assert.match(english, /leaves an existing `.github\/copilot-instructions\.md` unchanged/);
    assert.match(chinese, /已有 `.github\/copilot-instructions\.md`，其内容保持不变/);
  });
});
