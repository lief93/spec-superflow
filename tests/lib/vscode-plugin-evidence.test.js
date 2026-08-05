import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';

const ROOT = process.cwd();
const read = path => readFileSync(join(ROOT, path), 'utf8');

describe('VS Code Plugin documentation boundary', () => {
  it('keeps bootstrap implementation details in code and user setup steps in docs', () => {
    const productionMcp = JSON.parse(read('.mcp.json'));
    const server = read('servers/spec-superflow-mcp.mjs');
    const reference = read('docs/vscode-agent-plugin.md');
    const guide = read('docs/vscode-agent-plugin-zh.md');

    assert.ok(productionMcp.mcpServers['spec-superflow']);
    for (const tool of [
      'spec_superflow_cli_status',
      'spec_superflow_install_cli',
      'spec_superflow_optional_mcp_status',
      'spec_superflow_install_optional_mcp',
    ]) {
      assert.match(server, new RegExp(tool));
    }
    assert.doesNotMatch(server, /spec_superflow_run/);
    assert.match(reference, /one fixed allowlisted MCP call/i);
    assert.match(reference, /VS Code SecretStorage/i);
    assert.match(reference, /independent of[\s\S]*`\/workflow-init`/i);
    assert.match(guide, /固定白名单 MCP/i);
    assert.match(guide, /VS Code\s+SecretStorage/i);
    assert.match(guide, /Example MCP 与 `\/workflow-init` 相互独立/i);
  });

  it('documents workflow-init as the only install entry and local Plugin source ownership', () => {
    const reference = read('docs/vscode-agent-plugin.md');
    const guide = read('docs/vscode-agent-plugin-zh.md');

    assert.match(reference, /type `\/workflow-init`/i);
    assert.match(
      reference,
      /setup reports `READY`[\s\S]*select \*\*Spec Superflow\*\* and describe a\s+requirement/i,
    );
    assert.match(
      reference,
      /built-in \*\*Agent\*\*[\s\S]*type `\/workflow-init`[\s\S]*Click it or press \*\*Tab\*\*/i,
    );
    assert.match(
      guide,
      /VS Code 内置 \*\*Agent\*\*[\s\S]*输入 `\/workflow-init`[\s\S]*按 \*\*Tab\*\*/i,
    );
    assert.match(guide, /初始化返回 `READY`[\s\S]*选择 \*\*Spec Superflow\*\*/i);
    assert.match(reference, /Run `\/workflow-init` before starting a requirement/i);
    assert.match(guide, /`\/workflow-init` 只准备运行环境/i);
    assert.doesNotMatch(`${reference}\n${guide}`, /continues the original request once/i);
    assert.match(reference, /VSIX-bundled Agent Plugin only/i);
    assert.match(reference, /no second repository, registry, or archive is required/i);
  });

  it('keeps direct CLI and project instruction ownership in their authoritative files', () => {
    const workflow = read('skills/workflow-start/SKILL.md');
    const projectInit = read('skills/project-init/SKILL.md');
    const reference = read('docs/vscode-agent-plugin.md');
    const guide = read('docs/vscode-agent-plugin-zh.md');

    assert.match(workflow, /ssf state init/);
    assert.match(workflow, /ssf state transition/);
    assert.match(projectInit, /\.github\/instructions\/spec-superflow\.instructions\.md/);
    assert.match(projectInit, /Leave an existing `\.github\/copilot-instructions\.md` byte-for-byte unchanged/);
    assert.match(reference, /Skills execute `ssf state`/);
    assert.match(reference, /\.github\/instructions\/spec-superflow\.instructions\.md/);
    assert.match(guide, /`project-init` 生成/);
    assert.match(guide, /已有 `\.github\/copilot-instructions\.md`[\s\S]*保持不变/);
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
        /one `Spec Superflow` workflow Agent/i,
        /separate\s+`Matt Engineering` Agent/i,
        /exact(?:ly)? `Spec Superflow Reviewer`[\s\S]*no separate Dev Agent/i,
        /cross-stage[\s\S]*canar(?:y|ies)[\s\S]*(?:do not leak|absent)/i,
        /ordinary project-read and terminal tools[\s\S]*read-only Git[\s\S]*untracked canary[\s\S]*candidate identity[\s\S]*remain unchanged/i,
        /does not run tests or any workflow command except read-only[\s\S]*ssf review candidate[\s\S]*mutate Git[\s\S]*invoke another\s+Agent/i,
        /Reviewer[\s\S]*Primary[\s\S]*(?:repairs|asks the user)/i,
      ]],
      [chinese, [
        /一个 `Spec Superflow` 工作流 Agent/,
        /独立的\s+`Matt Engineering` Agent/,
        /精确(?:调用)? `Spec Superflow Reviewer`[\s\S]*没有注册或调用独立 Dev Agent/,
        /跨阶段 canary[\s\S]*(?:不泄漏|不存在)/,
        /普通项目读取\/终端工具[\s\S]*只读 Git 命令[\s\S]*untracked[\s\S]*candidate identity[\s\S]*完全不变/,
        /不运行测试或除只读[\s\S]*ssf review candidate[\s\S]*以外的工作流命令[\s\S]*不修改[\s\S]*Git[\s\S]*不调用其他 Agent/,
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

  it('documents the independent Matt Plugin, pinned source, and honest compatibility boundary', () => {
    const guide = read('docs/vscode-user-guide.md');
    const readme = read('extensions/spec-superflow-companion/README.md');
    const english = read('docs/vscode-agent-plugin.md');
    const chinese = read('docs/vscode-agent-plugin-zh.md');
    const changelog = read('CHANGELOG.md');
    const compatibility = JSON.parse(read(
      'extensions/spec-superflow-companion/matt-plugin/compatibility.json',
    ));
    const combined = `${guide}\n${readme}\n${english}\n${chinese}\n${changelog}`;

    assert.match(guide, /one VSIX[\s\S]*Spec Superflow[\s\S]*Matt Engineering/i);
    assert.match(guide, /ask-matt[\s\S]*explicit/i);
    assert.match(guide, /diagnosing-bugs[\s\S]*automatic/i);
    assert.match(readme, /two independent Agent Plugins/i);
    assert.match(english, /agent-plugin[\s\S]*matt-plugin/i);
    assert.match(chinese, /agent-plugin[\s\S]*matt-plugin/i);
    assert.match(combined, /2ab958093e83e0ec752e6c1c5932da465bf23e0c/);
    assert.match(combined, /22 Skills[\s\S]*66 files/i);
    assert.match(english, /ordinary build[\s\S]*offline[\s\S]*explicit\s+sync/i);
    assert.match(chinese, /普通构建[\s\S]*离线[\s\S]*显式\s+sync/i);
    assert.match(combined, /code-review[\s\S]*research[\s\S]*wayfinder[\s\S]*PENDING/i);
    assert.equal(compatibility.skills.length, 22);
    assert.equal(compatibility.skills.every(entry => entry.status === 'PENDING'), true);
    assert.doesNotMatch(combined, /all 22 Skills (?:are )?(?:verified|supported)/i);
  });
});
