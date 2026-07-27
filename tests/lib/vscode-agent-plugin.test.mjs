import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { describe, it } from 'node:test';

const ROOT = process.cwd();
const read = path => readFileSync(join(ROOT, path), 'utf8');

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

    assert.match(command, /^name: workflow-init$/m);
    assert.match(command, /^agent: Spec Superflow$/m);
    assert.doesNotMatch(command, /^allowed-tools:/m);
    assert.match(command, /tools:\s*\n\s+- ['"]spec-superflow\/\*['"]/);
    assert.match(command, /\n\s+- ['"]spec-superflow-optional-example\/\*['"]/);
    assert.match(command, /\n\s+- ['"]vscode\/askQuestions['"]/);
    assert.equal(existsSync(join(ROOT, 'agents', 'workflow-init.agent.md')), false);
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
    assert.match(command, /instead of the Agent's `workflow-start` route/);
    assert.match(
      command,
      new RegExp(`spec-superflow-plugin-version: ${pkg.version.replaceAll('.', '\\.')}`),
    );
    assert.doesNotMatch(command, /tgz|https?:\/\/|npm view|@latest/);
    assert.doesNotMatch(command, /run `ssf --version`|npm install -g/i);
    assert.match(command, /create task artifacts, or start the\s+development workflow/);
    assert.match(
      command,
      /first action is #tool:spec-superflow\/spec_superflow_cli_status/i,
    );
    assert.match(
      command,
      /after the CLI is verified[^.]*next and only tool call[^.]*spec_superflow_optional_mcp_status/is,
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
    assert.match(chinese, /鼠标点击或按 \*\*Tab\*\*[\s\S]*结构化 Slash Command/);
    assert.match(chinese, /`name`、`description`、`agent` 和 `tools`/);
    assert.match(chinese, /不使用 `allowed-tools`/);
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
    assert.doesNotMatch(normalWorkflow, /spec_superflow_cli_status|spec_superflow_install_cli/);
    assert.doesNotMatch(
      normalWorkflow,
      /spec_superflow_optional_mcp_status|spec_superflow_install_optional_mcp/,
    );
    assert.match(normalWorkflow, /start or resume development through the linked `workflow-start` skill/i);
    assert.match(agent, /`workflow-start` is a linked Agent Skill, not\s+an `ssf` CLI subcommand/i);
    assert.match(agent, /never\s+run \`ssf workflow-start\`/i);
    assert.match(agent, /execute the global `ssf` CLI directly/i);
    assert.doesNotMatch(agent, /spec_superflow_run|logical\s+command|Do not invoke a PATH-installed/);
    assert.match(agent, /Do not run `ssf inject` inside this agent/);
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

});
