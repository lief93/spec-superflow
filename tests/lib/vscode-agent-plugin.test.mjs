import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { describe, it } from 'node:test';

const ROOT = process.cwd();
const read = path => readFileSync(join(ROOT, path), 'utf8');
const primary = read('agents/spec-superflow.agent.md');
const reviewer = read('agents/spec-superflow-reviewer.agent.md');
const setup = read('agents/spec-superflow-setup.agent.md');

function probeAgentRouteWithoutNode(route) {
  return spawnSync(
    process.execPath,
    [
      '-e',
      `
        const { readFileSync } = require('node:fs');
        const agent = readFileSync(process.argv[1], 'utf8');
        const frontmatter = agent.slice(0, agent.indexOf('\\n---', 4));
        const normalWorkflow = agent.slice(
          agent.indexOf('# Spec Superflow Agent'),
          agent.indexOf('## /workflow-init Protocol'),
        );
        if (/PreToolUse|command -v node|where node|node -e|SSF_PLUGIN_VERSION/.test(frontmatter)) {
          process.exit(2);
        }
        if (/spec_superflow_cli_status|spec_superflow_install_cli|check CLI readiness/i.test(normalWorkflow)) {
          process.exit(3);
        }
        if (process.argv[2] === 'project-init' && !/route from \`workflow-start\` to \`project-init\`/i.test(normalWorkflow)) {
          process.exit(4);
        }
      `,
      join(ROOT, 'agents', 'spec-superflow.agent.md'),
      route,
    ],
    {
      env: {
        PATH: '',
      },
      encoding: 'utf8',
    },
  );
}

describe('VS Code Agent Plugin', () => {
  it('exposes one visible Primary and one hidden fixed Reviewer', () => {
    const agentFiles = readdirSync(join(ROOT, 'agents'))
      .filter(file => file.endsWith('.agent.md'))
      .sort();

    assert.deepEqual(agentFiles, [
      'spec-superflow-reviewer.agent.md',
      'spec-superflow-setup.agent.md',
      'spec-superflow.agent.md',
    ]);
    assert.match(primary, /^agents: \["Spec Superflow Reviewer"\]$/m);
    assert.match(primary, /^user-invocable: true$/m);
    assert.match(reviewer, /^user-invocable: false$/m);
    assert.match(reviewer, /^agents: \[\]$/m);
    assert.doesNotMatch(reviewer, /^tools:/m);
    assert.match(setup, /^user-invocable: false$/m);
    assert.match(setup, /^disable-model-invocation: true$/m);
    assert.doesNotMatch(primary, /Spec Superflow Setup/);
  });

  it('adds only three exact-full independent semantic checkpoints to the Primary', () => {
    assert.match(primary, /one independent Reviewer context at each of[\s\S]*exactly three[\s\S]*proposal-specs[\s\S]*design-tasks[\s\S]*final/i);
    assert.match(primary, /Freeze the current stage inputs[\s\S]*only the exact Change directory and stage[\s\S]*pending-report\.json[\s\S]*record[\s\S]*check/i);
    assert.match(primary, /first verified `Request Changes`[\s\S]*repairs only the affected\s+stage exactly once[\s\S]*same Reviewer context/i);
    assert.match(primary, /second verified `Request Changes`[\s\S]*`BLOCKED`[\s\S]*no\s+third review/i);
    assert.match(primary, /DP-2 and the existing user-owned DP-3[\s\S]*remain separate/i);
    assert.doesNotMatch(primary, /dp_3_contract_hash/i);
    assert.match(primary, /hotfix.*tweak[\s\S]*do not invoke or require/i);
  });

  it('keeps the Reviewer behavior read-only while retaining ordinary project and terminal tools', () => {
    assert.match(
      reviewer,
      /ordinary project-read and terminal tools[\s\S]*git status[\s\S]*git diff/i,
    );
    assert.match(
      reviewer,
      /Do not edit[^]*stage[^]*commit[^]*push[^]*change workflow state[^]*invoke another Agent/i,
    );
    assert.match(reviewer, /proposal-specs[\s\S]*design-tasks[\s\S]*final/i);
    assert.match(reviewer, /one unfenced JSON object/i);
  });

  it('registers the bundled agent, skills, commands, and MCP bridge', () => {
    const manifest = JSON.parse(read('.plugin/plugin.json'));
    const mcp = JSON.parse(read('.mcp.json'));

    assert.equal(manifest.skills, 'skills/');
    assert.equal(manifest.agents, 'agents/');
    assert.equal(manifest.commands, 'commands/');
    assert.equal(manifest.mcpServers, '.mcp.json');
    assert.deepEqual(
      manifest.hooks,
      {},
      'OpenPlugin must suppress Claude-format hook auto-discovery in VS Code',
    );
    assert.deepEqual(mcp.mcpServers['spec-superflow'], {
      command: '${PLUGIN_ROOT}/servers/spec-superflow-mcp-launcher.cmd',
      args: ['${PLUGIN_ROOT}/servers/spec-superflow-mcp.mjs'],
      cwd: '${PLUGIN_ROOT}',
    });
    assert.equal(
      existsSync(join(ROOT, 'servers', 'spec-superflow-mcp-launcher.cmd')),
      true,
    );
    assert.equal(existsSync(join(ROOT, 'servers', 'spec-superflow-mcp.mjs')), true);
  });

  it('keeps credential prompts out of the production Plugin MCP config', () => {
    const mcp = JSON.parse(read('.mcp.json'));

    assert.equal(mcp.inputs, undefined);
    assert.equal(mcp.mcpServers['spec-superflow-token-example'], undefined);
  });

  it('packages a token-prompt user MCP example around the bundled stdio server', () => {
    const example = JSON.parse(read('examples/mcp/token-auth/user-mcp.example.json'));

    assert.deepEqual(example.inputs, [
      {
        type: 'promptString',
        id: 'spec-superflow-optional-mcp-url',
        description: 'Service URL for the optional Spec Superflow MCP',
        password: false,
      },
      {
        type: 'promptString',
        id: 'spec-superflow-optional-mcp-token',
        description: 'Token for the optional Spec Superflow MCP',
        password: false,
      },
    ]);
    assert.equal(example.inputs.every(input => input.password === false), true);
    assert.deepEqual(example.servers['spec-superflow-optional-example'], {
      type: 'stdio',
      command: '<absolute-path-to-plugin>/servers/spec-superflow-mcp-launcher.cmd',
      args: ['<absolute-path-to-plugin>/servers/token-example-mcp.mjs'],
      env: {
        SPEC_SUPERFLOW_EXAMPLE_URL: '${input:spec-superflow-optional-mcp-url}',
        SPEC_SUPERFLOW_EXAMPLE_TOKEN: '${input:spec-superflow-optional-mcp-token}',
      },
    });
    assert.equal(existsSync(join(ROOT, 'servers', 'token-example-mcp.mjs')), true);
    assert.equal(existsSync(join(ROOT, 'examples', 'mcp', 'token-auth', 'README.md')), true);
  });

  it('declares every input referenced by the packaged MCP example', () => {
    const example = JSON.parse(read('examples/mcp/token-auth/user-mcp.example.json'));
    const declared = new Set(example.inputs.map(input => input.id));
    const referenced = [...JSON.stringify(example.servers).matchAll(/\$\{input:([^}]+)\}/g)]
      .map(match => match[1]);

    assert.notEqual(referenced.length, 0);
    for (const id of referenced) {
      assert.equal(declared.has(id), true, `MCP example references undeclared input: ${id}`);
    }
  });

  it('provides an explicit CLI bootstrap workflow-init command', () => {
    const pkg = JSON.parse(read('package.json'));
    const command = read('commands/workflow-init.md');
    const setupAgent = read('agents/spec-superflow-setup.agent.md');

    assert.match(command, /^name: workflow-init$/m);
    assert.match(command, /^agent: Spec Superflow Setup$/m);
    assert.doesNotMatch(command, /^agent: Spec Superflow$/m);
    assert.match(
      command,
      /initialize, verify, or update the Spec Superflow workflow runtime/i,
    );
    assert.match(
      command,
      /do not ask for[^.]*change name[^.]*requirement[^.]*scope[^.]*acceptance criteria/is,
    );
    assert.doesNotMatch(command, /^allowed-tools:/m);
    assert.match(command, /tools:\s*\n\s+- ['"]spec-superflow\/\*['"]/);
    assert.match(command, /\n\s+- ['"]spec-superflow-optional-example\/\*['"]/);
    assert.match(command, /\n\s+- ['"]vscode\/askQuestions['"]/);
    assert.match(setupAgent, /^name: Spec Superflow Setup$/m);
    assert.match(setupAgent, /^user-invocable: false$/m);
    assert.match(setupAgent, /^disable-model-invocation: true$/m);
    assert.match(setupAgent, /tools:\s*\n\s+- ['"]spec-superflow\/\*['"]/);
    assert.match(setupAgent, /\n\s+- ['"]spec-superflow-optional-example\/\*['"]/);
    assert.match(setupAgent, /\n\s+- ['"]vscode\/askQuestions['"]/);
    assert.match(setupAgent, /never\s+call tools in parallel/i);
    assert.doesNotMatch(
      setupAgent,
      /terminal|shell|read(?:ing)? (?:the )?workspace|workflow-start|project-init|state init/i,
    );
    assert.match(command, /spec_superflow_cli_status/);
    assert.match(command, /spec_superflow_install_cli/);
    assert.match(
      command,
      /askQuestions[\s\S]*install or update\s+the global `ssf` command/i,
    );
    assert.match(command, /spec_superflow_optional_mcp_status/);
    assert.match(command, /spec_superflow_install_optional_mcp/);
    for (const tool of [
      'spec_superflow_cli_status',
      'spec_superflow_install_cli',
      'spec_superflow_optional_mcp_status',
      'spec_superflow_install_optional_mcp',
    ]) {
      assert.match(command, new RegExp(`#tool:spec-superflow/${tool}`));
    }
    assert.match(command, /request confirmation/i);
    assert.match(command, /status tool executes `ssf --version`/i);
    assert.match(command, /do not route to project-init\s+or workflow-start/i);
    assert.doesNotMatch(command, /alternate (?:installation|path)/i);
    assert.match(
      command,
      new RegExp(`spec-superflow-plugin-version: ${pkg.version.replaceAll('.', '\\.')}`),
    );
    assert.doesNotMatch(command, /tgz|https?:\/\/|npm view|@latest/);
    assert.doesNotMatch(command, /run `ssf --version`|npm install -g/i);
    assert.match(command, /create task artifacts[\s\S]*start\s+or resume the development workflow/);
    assert.match(
      command,
      /first action is #tool:spec-superflow\/spec_superflow_cli_status/i,
    );
    assert.match(
      command,
      /after the CLI is\s+verified[^.]*next and only tool call[^.]*spec_superflow_optional_mcp_status/is,
    );
    assert.match(
      command,
      /do not read[^.]*workspace[^.]*file[^.]*Skill/is,
    );
    assert.match(command, /workflow.*READY.*optionalMcp.*SKIPPED/is);
    assert.match(
      command,
      /must not report.*optionalMcp=SKIPPED.*unless.*askQuestions.*No/is,
    );
    assert.match(command, /visible native input[\s\S]*verify both values/i);
    assert.match(command, /URL and Token[\s\S]*VS Code[\s\S]*secure/i);
    assert.match(command, /workflow=READY, optionalMcp=REGISTERED/);
    assert.match(command, /MCP: List Servers[\s\S]*Start Server/i);
    assert.match(
      command,
      /do not use #tool:vscode\/askQuestions[^.]*URL[^.]*Token/is,
    );
    assert.doesNotMatch(command, /ask the user to paste.*token|token.*chat/i);
  });

  it('documents selecting workflow-init as a structured VS Code Slash Command', () => {
    const english = read('docs/vscode-agent-plugin.md');
    const chinese = read('docs/vscode-agent-plugin-zh.md');

    assert.match(english, /Click it or press \*\*Tab\*\*[\s\S]*structured Slash Command/i);
    assert.match(english, /`name`, target `agent`, and restricted `tools`/);
    assert.match(english, /`allowed-tools` is not a VS Code\s+prompt-file field/i);
    assert.match(english, /hidden \*\*Spec Superflow Setup\*\* Agent/i);
    assert.match(english, /only the bootstrap MCP and native question tool/i);
    assert.match(english, /does not[\s\S]*create a Change[\s\S]*start or resume development/i);
    assert.match(chinese, /选择 Plugin 提供的候选项[\s\S]*按 \*\*Tab\*\*/i);
    assert.match(chinese, /`\/workflow-init` 只准备运行环境/i);
    assert.match(chinese, /不读取当前项目[\s\S]*不生成 change[\s\S]*不启动需求/i);
  });

  it('keeps Plugin setup commands outside the development state machine', () => {
    const pkg = JSON.parse(read('package.json'));
    const agent = read('agents/spec-superflow.agent.md');

    assert.match(agent, /Execute an explicitly selected Plugin command as written/);
    assert.match(agent, /\/workflow-init Protocol/);
    assert.match(agent, /first tool\s+invocation must be `spec_superflow_cli_status`/i);
    assert.match(agent, /must not route through `workflow-start`/);
    assert.match(agent, /do not inspect the workspace, load a\s+Skill, or create task artifacts/i);
    assert.match(
      agent,
      new RegExp(`CLI versions are exactly ${pkg.version.replaceAll('.', '\\.')}`),
    );
    assert.match(agent, /Report `READY` only when the second status call reports `ready: true`/);
  });

  it('provides an opt-in Agent whose normal workflow assumes workflow-init completed', () => {
    const agent = read('agents/spec-superflow.agent.md');
    const normalWorkflow = agent.slice(
      agent.indexOf('# Spec Superflow Agent'),
      agent.indexOf('## /workflow-init Protocol'),
    );

    assert.match(agent, /name: Spec Superflow/);
    assert.match(agent, /user-invocable: true/);
    assert.match(agent, /disable-model-invocation: true/);
    assert.match(agent, /spec_superflow_cli_status/);
    assert.match(agent, /spec_superflow_install_cli/);
    assert.match(agent, /spec_superflow_optional_mcp_status/);
    assert.match(agent, /spec_superflow_install_optional_mcp/);
    assert.doesNotMatch(normalWorkflow, /spec_superflow_cli_status|spec_superflow_install_cli/);
    assert.doesNotMatch(
      normalWorkflow,
      /spec_superflow_optional_mcp_status|spec_superflow_install_optional_mcp/,
    );
    assert.doesNotMatch(normalWorkflow, /Development Entry Protocol/);
    assert.match(normalWorkflow, /start or resume development through the linked `workflow-start` skill/i);
    assert.match(
      agent,
      /`workflow-start` is a linked Agent Skill, not\s+an `ssf` CLI subcommand/i,
    );
    assert.match(agent, /never\s+run `ssf workflow-start`/i);
    assert.match(
      agent,
      /load the linked `spec-writer` Skill before generating or repairing/is,
    );
    assert.match(
      agent,
      /Do not inspect\s+a user-level\s+or globally installed `spec-superflow` package/is,
    );
    assert.match(
      agent,
      /Do not inspect implementation source, edit code, or edit tests directly\.\s+First enter `workflow-start`/i,
    );
    assert.match(
      agent,
      /planning artifacts\s+and\s+an\s+approved\s+execution contract exist/i,
    );
    assert.match(
      agent,
      /planning artifacts must\s+pass `ssf validate\s+<change-dir>` before any implementation edit/i,
    );
    assert.match(
      agent,
      /final response.*`ssf validate <change-dir>`.*`ssf state check <change-dir>`/is,
    );
    assert.match(agent, /execute the global `ssf` CLI directly/i);
    assert.doesNotMatch(agent, /spec_superflow_run|logical\s+command|Do not invoke a PATH-installed/);
    assert.match(agent, /Do not run `ssf inject` inside this agent/);
    assert.match(agent, /copilot-instructions\.md` remains unchanged/);
    assert.match(agent, /Do not copy centrally maintained agents, skills, scripts, or templates/);
    assert.doesNotMatch(agent, /hooks:\s+PreToolUse:/);
    assert.doesNotMatch(agent, /\$\{PLUGIN_ROOT\}/);
    assert.doesNotMatch(agent, /command -v node|where node|SSF_PLUGIN_VERSION|node -e/);
  });

  it('keeps optional MCP setup from blocking workflow initialization', () => {
    const command = read('commands/workflow-init.md');
    const agent = read('agents/spec-superflow.agent.md');

    for (const content of [command, agent]) {
      assert.match(content, /business MCP is optional/i);
      assert.match(content, /workflow.*READY.*optionalMcp.*SKIPPED/is);
      assert.match(content, /workflow.*READY.*optionalMcp.*REGISTERED/is);
      assert.match(content, /declines? optional MCP, it does not block/i);
      assert.match(content, /do not pass[^.]*URL[^.]*Token[^.]*tool argument/is);
      assert.match(content, /MCP: List Servers[\s\S]*Start Server/i);
    }
  });

  it('does not probe Node, npm, or the CLI for ordinary tools or project-init', () => {
    for (const route of ['ordinary-tool', 'project-init']) {
      const probe = probeAgentRouteWithoutNode(route);
      assert.equal(
        probe.status,
        0,
        `${route} must remain routable with no Node executable on PATH: ${probe.stderr}`,
      );
    }
  });

  it('keeps workflow commands independent of repository-local scripts', () => {
    const workflow = read('skills/workflow-start/SKILL.md');

    assert.doesNotMatch(workflow, /CLAUDE_PLUGIN_ROOT|node scripts\//);
    assert.doesNotMatch(workflow, /spec_superflow_cli_status|spec_superflow_install_cli/);
    assert.doesNotMatch(workflow, /ensure the matching CLI is available/i);
    assert.doesNotMatch(
      workflow,
      /check CLI readiness|prompt (?:for|to install) (?:the )?CLI|route to `?workflow-init`?|install (?:or update )?(?:the )?CLI/i,
    );
    assert.doesNotMatch(workflow, /`ssf check-update`|npm view|@latest/);
    assert.match(workflow, /`ssf infer-workflow <change-dir>`/);
    assert.match(workflow, /`ssf guard check <dir>/);
  });

  it('keeps workflow runtime setup out of development skills', () => {
    const workflow = read('skills/workflow-start/SKILL.md');
    const projectInit = read('skills/project-init/SKILL.md');

    assert.match(workflow, /^disable-model-invocation: true$/m);
    for (const skill of [workflow, projectInit]) {
      assert.match(skill, /do not invoke[^.]*`?\/workflow-init`?/i);
      assert.match(skill, /Plugin, CLI, or MCP runtime setup/i);
      assert.match(skill, /return\s+control to the selected command/i);
      assert.match(skill, /do not inspect the workspace/i);
      assert.match(skill, /create or resume a Change/i);
    }
  });

  it('initializes a new change before routing and keeps planning artifacts inside it', () => {
    const workflow = read('skills/workflow-start/SKILL.md');
    const writer = read('skills/spec-writer/SKILL.md');

    assert.match(workflow, /`ssf state init changes\/<change-name>`/);
    assert.match(
      workflow,
      /initialize the exact\s+`changes\/<change-name>` directory before recording DP-0/i,
    );
    assert.match(
      workflow,
      /Do not create `proposal\.md`, `design\.md`, `tasks\.md`, or delta specs at the repository root/i,
    );
    assert.match(writer, /`<change-dir>\/proposal\.md`/);
    assert.match(writer, /`<change-dir>\/specs\/<capability>\/spec\.md`/);
    assert.match(writer, /`<change-dir>\/design\.md`/);
    assert.match(writer, /`<change-dir>\/tasks\.md`/);
    assert.match(
      writer,
      /All generated planning artifacts must stay under the active `<change-dir>`/i,
    );
    assert.match(
      writer,
      /Never create planning artifacts at the\s+repository root/i,
    );
    assert.match(
      workflow,
      /Route to spec-writer[\s\S]*guard check <dir> exploring specifying[\s\S]*state transition <dir> specifying/i,
    );
    assert.match(
      workflow,
      /Route to contract-builder[\s\S]*guard check <dir> specifying bridging[\s\S]*state transition <dir> bridging/i,
    );
    assert.match(
      workflow,
      /Route to build-executor[\s\S]*guard check <dir> bridging approved-for-build[\s\S]*state transition <dir> approved-for-build[\s\S]*guard check <dir> approved-for-build executing[\s\S]*state transition <dir> executing/i,
    );
    const releaseRoute = /### Route to release-archivist([\s\S]*?)(?=\n### )/
      .exec(workflow)?.[1] || '';
    assert.match(releaseRoute, /release-archivist[\s\S]*own the\s+`executing` → `closing`\s+transition/i);
    assert.match(releaseRoute, /state get <dir> state[\s\S]*require\s+`closing`/i);
    assert.doesNotMatch(releaseRoute, /guard check <dir> executing closing|state transition <dir> closing/i);
  });

  it('makes validator-sensitive planning structure explicit and preserves approval gates', () => {
    const agent = read('agents/spec-superflow.agent.md');
    const workflow = read('skills/workflow-start/SKILL.md');
    const writer = read('skills/spec-writer/SKILL.md');

    assert.match(
      writer,
      /every non-`No design change` value in the coverage table must exactly match a `### Decision: <title>` heading/i,
    );
    assert.match(
      writer,
      /Requirement and Scenario cells contain only the exact titles.*without `Requirement:` or `Scenario:` prefixes/i,
    );
    assert.match(
      writer,
      /^\| Requirement \| Scenario \| Design Decision \| Affected Area \| Baseline \/ Reuse \| Constraint \/ Deviation \| Why Here \|$/m,
    );
    assert.match(writer, /^\| <exact Requirement title> \| <exact Scenario title> \| <exact Decision title> \|/m);
    assert.match(writer, /^## Batch 1: <goal>$/m);
    assert.match(writer, /^- \*\*Requirement\*\*: <exact Requirement title>$/m);
    assert.match(writer, /^- \*\*User-visible\*\*: (?:Yes|No)$/m);
    assert.match(writer, /^#### File Changes$/m);
    assert.match(writer, /^##### (?:Create|Modify|Delete) `path\/to\/file`$/m);
    assert.match(writer, /^#### TDD Test Plan$/m);
    assert.match(writer, /^### Batch Verification$/m);
    assert.match(writer, /do not\s+replace these headings with bold list labels/i);
    assert.match(
      writer,
      /Stop after each artifact and\s+wait for explicit user confirmation before generating the next/i,
    );
    assert.match(
      agent,
      /create at most one planning artifact family in a single\s+response/i,
    );
    assert.match(
      agent,
      /return to the user immediately after presenting that artifact/i,
    );
    assert.match(
      writer,
      /Never generate `execution-contract\.md`; only `contract-builder` owns that\s+artifact/i,
    );
    assert.match(
      agent,
      /Never collapse DP-2 planning approval and DP-3 execution-contract approval\s+into one gate/i,
    );
    assert.match(
      workflow,
      /When the user explicitly requests the full workflow, persist `workflow` as\s+`full` and do not infer `hotfix` or `tweak`/i,
    );
  });

  it('requires dependency-closed planning and precise behavioral test seams', () => {
    const writer = read('skills/spec-writer/SKILL.md');
    const contract = read('skills/contract-builder/SKILL.md');

    for (const content of [writer, contract]) {
      assert.match(
        content,
        /interface[\s\S]*production implementation[\s\S]*(?:fake|mock)[\s\S]*test double/i,
      );
      assert.match(content, /affected module[\s\S]*(?:compile|test) obligation/i);
      assert.match(
        content,
        /required edge case[\s\S]*(?:fixture|precondition)[\s\S]*observable assertion/i,
      );
      assert.match(
        content,
        /injectable rendering seam[\s\S]*state-to-UI derivation[\s\S]*(?:lazy|scrolling|repeated content)/i,
      );
    }
    assert.match(
      writer,
      /do not stop at the first implementation found/i,
    );
    assert.match(
      writer,
      /one item disappearing does not prove an empty-result state/i,
    );
    assert.match(
      writer,
      /Do not claim state mapping is covered by asserting only a child component parameter/i,
    );
  });

  it('keeps bootstrap checks out of internal workflow skills', () => {
    const skillNames = readdirSync(join(ROOT, 'skills'), { withFileTypes: true })
      .filter(entry => entry.isDirectory())
      .map(entry => entry.name);

    for (const skill of skillNames) {
      const content = read(`skills/${skill}/SKILL.md`);
      assert.doesNotMatch(
        content,
        /spec_superflow_cli_status|spec_superflow_install_cli|install the CLI/i,
        `${skill} must rely on workflow-init having completed`,
      );
    }
  });

  it('links every workflow skill from the selected agent', () => {
    const agent = read('agents/spec-superflow.agent.md');
    const links = [...agent.matchAll(/\]\(\.\.\/skills\/([^/]+)\/SKILL\.md\)/g)]
      .map(match => match[1]);

    assert.equal(links.length, 11);
    for (const skill of links) {
      assert.equal(existsSync(join(ROOT, 'skills', skill, 'SKILL.md')), true);
    }
  });

  it('requires fresh artifact and state verification before completion', () => {
    const executor = read('skills/build-executor/SKILL.md');
    const release = read('skills/release-archivist/SKILL.md');

    assert.match(
      executor,
      /mark every completed `tasks\.md` TDD checkbox as `\[x\]` before recording the batch complete/i,
    );
    assert.match(
      executor,
      /`ssf state set <change-dir> batches_completed <N>` only after those checkboxes are updated/i,
    );
    assert.match(release, /^## AC Test Evidence$/m);
    assert.match(
      release,
      /^\| Requirement \| AC \| Layer \| Platform \| Test File \| Test Case \| Result \| Command \| Evidence \|$/m,
    );
    assert.match(
      release,
      /copy Requirement and AC from the owning task section[\s\S]*`tasks\.md > TDD Test Plan` row/i,
    );
    assert.match(
      release,
      /update every completed `tasks\.md` checkbox to `\[x\]` before attempting `closing`/i,
    );
    assert.match(
      release,
      /run `ssf guard check <change-dir> executing closing --json` before `ssf state transition <change-dir> closing`/i,
    );
    assert.match(release, /after every final artifact edit, run `ssf validate <change-dir>`/i);
    assert.match(release, /run `ssf state check <change-dir>`/i);
    assert.match(release, /do not claim completion/i);
  });
});
