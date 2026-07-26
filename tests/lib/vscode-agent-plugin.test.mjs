import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, it } from 'node:test';

const ROOT = process.cwd();
const read = path => readFileSync(join(ROOT, path), 'utf8');

describe('VS Code Agent Plugin', () => {
  it('registers the bundled agent, skills, commands, and MCP bridge', () => {
    const manifest = JSON.parse(read('.plugin/plugin.json'));
    const mcp = JSON.parse(read('.mcp.json'));

    assert.equal(manifest.skills, 'skills/');
    assert.equal(manifest.agents, 'agents/');
    assert.equal(manifest.commands, 'commands/');
    assert.equal(manifest.mcpServers, '.mcp.json');
    assert.deepEqual(mcp.mcpServers['spec-superflow'], {
      command: 'node',
      args: ['${PLUGIN_ROOT}/servers/spec-superflow-mcp.mjs'],
      cwd: '${PLUGIN_ROOT}',
    });
    assert.equal(existsSync(join(ROOT, 'servers', 'spec-superflow-mcp.mjs')), true);
  });

  it('provides a bundled-runtime workflow-init command', () => {
    const pkg = JSON.parse(read('package.json'));
    const command = read('commands/workflow-init.md');

    assert.match(command, /name: workflow-init/);
    assert.match(command, /spec_superflow_health/);
    assert.match(command, /bundled Plugin runtime/);
    assert.match(command, /instead of the Agent's `workflow-start` route/);
    assert.match(
      command,
      new RegExp(`spec-superflow-plugin-version: ${pkg.version.replaceAll('.', '\\.')}`),
    );
    assert.doesNotMatch(command, /npm|tgz|registry|package=<|install -g/);
    assert.match(command, /create task artifacts, or start the\s+development workflow/);
  });

  it('keeps Plugin setup commands outside the development state machine', () => {
    const agent = read('agents/spec-superflow.agent.md');

    assert.match(agent, /Execute an explicitly selected Plugin command as written/);
    assert.match(agent, /workflow-init[\s\S]*must not route through/);
    assert.match(agent, /inspect the workspace, or create task artifacts/);
  });

  it('provides an opt-in Agent that uses the bundled MCP runtime', () => {
    const agent = read('agents/spec-superflow.agent.md');

    assert.match(agent, /name: Spec Superflow/);
    assert.match(agent, /user-invocable: true/);
    assert.match(agent, /disable-model-invocation: true/);
    assert.match(agent, /spec_superflow_run/);
    assert.match(agent, /Do not invoke a PATH-installed\s+`ssf`/);
    assert.match(agent, /Do not run `ssf inject` inside this agent/);
    assert.match(agent, /copilot-instructions\.md` remains owned by the target repository/);
    assert.match(agent, /Do not copy centrally maintained agents, skills, scripts, or templates/);
  });

  it('keeps workflow commands independent of repository-local scripts', () => {
    const workflow = read('skills/workflow-start/SKILL.md');

    assert.doesNotMatch(workflow, /CLAUDE_PLUGIN_ROOT|node scripts\//);
    assert.match(workflow, /`ssf check-update`/);
    assert.match(workflow, /`ssf infer-workflow <change-dir>`/);
    assert.match(workflow, /`ssf guard check <dir>/);
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
