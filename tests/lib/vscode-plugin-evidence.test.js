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

  it('documents Planning reading depth and implementation confirmation consistently', () => {
    const english = read('docs/vscode-agent-plugin.md');
    const chinese = read('docs/vscode-agent-plugin-zh.md');

    assert.match(
      english,
      /Proposal\s+and\s+Specs[\s\S]*goals[\s\S]*scope[\s\S]*behaviors[\s\S]*non-goals/i,
    );
    assert.match(
      chinese,
      /Proposal\s+和\s+Specs[\s\S]*目标[\s\S]*范围[\s\S]*行为[\s\S]*非目标/,
    );
    assert.match(
      english,
      /Design\s+and\s+Tasks[\s\S]*concise summary[\s\S]*complete `design\.md` and `tasks\.md`[\s\S]*reading depth[\s\S]*implementation direction/i,
    );
    assert.match(
      chinese,
      /Design\s+和\s+Tasks[\s\S]*简明摘要[\s\S]*完整 `design\.md` 和 `tasks\.md`[\s\S]*阅读深度[\s\S]*实现方向/,
    );
    assert.match(english, /real VS Code[\s\S]*PENDING/i);
    assert.match(chinese, /真实 VS Code[\s\S]*PENDING/i);
  });

  it('documents one same-context re-review per stage consistently', () => {
    const english = read('docs/vscode-agent-plugin.md');
    const chinese = read('docs/vscode-agent-plugin-zh.md');

    assert.match(english, /each stage[\s\S]*initial review[\s\S]*fresh isolated context/i);
    assert.match(
      english,
      /first `Request Changes`[\s\S]*same Reviewer context[\s\S]*second `Request Changes`[\s\S]*`BLOCKED`/i,
    );
    assert.match(chinese, /每个阶段[\s\S]*首次 Review[\s\S]*全新的隔离上下文/);
    assert.match(
      chinese,
      /第一次 `Request Changes`[\s\S]*同一个 Reviewer 上下文[\s\S]*第二次 `Request Changes`[\s\S]*`BLOCKED`/,
    );
  });

  it('keeps real Agent runtime acceptance PENDING until one combined run passes', () => {
    const english = read('docs/vscode-agent-plugin.md');
    const chinese = read('docs/vscode-agent-plugin-zh.md');

    for (const [content, labels] of [
      [english, [
        /only `Spec Superflow`/i,
        /exact(?:ly)? `Spec Superflow Reviewer`[\s\S]*no separate Dev Agent/i,
        /cross-stage[\s\S]*canar(?:y|ies)[\s\S]*(?:do not leak|absent)/i,
        /ordinary project-read and terminal tools[\s\S]*read-only Git[\s\S]*untracked canary[\s\S]*candidate identity[\s\S]*remain unchanged/i,
        /does not run tests or workflow commands[\s\S]*mutate Git[\s\S]*invoke another\s+Agent/i,
        /Reviewer[\s\S]*Primary[\s\S]*(?:repairs|asks the user)/i,
      ]],
      [chinese, [
        /只有 `Spec Superflow`/,
        /精确(?:调用)? `Spec Superflow Reviewer`[\s\S]*没有注册或调用独立 Dev Agent/,
        /跨阶段 canary[\s\S]*(?:不泄漏|不存在)/,
        /普通项目读取\/终端工具[\s\S]*只读 Git 命令[\s\S]*untracked[\s\S]*candidate identity[\s\S]*完全不变/,
        /不运行测试或工作流命令[\s\S]*不修改[\s\S]*Git[\s\S]*不调用其他 Agent/,
        /Reviewer[\s\S]*Primary[\s\S]*(?:修复|询问用户)/,
      ]],
    ]) {
      for (const label of labels) assert.match(content, label);
      assert.match(content, /VS Code 1\.123[\s\S]*PENDING/i);
      assert.match(content, /automation[\s\S]*Unavailable/i);
      assert.doesNotMatch(
        content,
        /(?:static|静态)[^\n]*(?:proves|证明)[^\n]*(?:picker|invocation|isolation|tool denial|mediation|调用|隔离|工具拒绝|中介)/i,
      );
    }
  });
});
