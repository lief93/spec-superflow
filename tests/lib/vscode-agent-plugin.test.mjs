import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, it } from 'node:test';

const ROOT = process.cwd();

function read(path) {
  return readFileSync(join(ROOT, path), 'utf8');
}

describe('VS Code Agent Plugin', () => {
  it('registers skills, agents, and the MCP configuration', () => {
    const manifest = JSON.parse(read('.plugin/plugin.json'));
    const mcp = JSON.parse(read('.mcp.json'));

    assert.equal(manifest.skills, 'skills/');
    assert.equal(manifest.agents, 'agents/');
    assert.equal(manifest.commands, 'commands/');
    assert.equal(manifest.mcpServers, '.mcp.json');
    assert.deepEqual(mcp, { mcpServers: {} });
  });

  it('provides a version-pinned workflow-init command', () => {
    const pkg = JSON.parse(read('package.json'));
    const command = read('commands/workflow-init.md');

    assert.match(command, /name: workflow-init/);
    assert.match(command, /node --version/);
    assert.match(command, /Node\.js 22 or newer/);
    assert.match(command, /ssf --version/);
    assert.match(command, /instead of the Agent's `workflow-start` route/);
    assert.match(command, /Do not inspect the open\s+workspace/);
    assert.match(
      command,
      new RegExp(`npm install -g spec-superflow@${pkg.version.replaceAll('.', '\\.')}`),
    );
    assert.match(command, /package=<path>/);
    assert.match(
      command,
      new RegExp(`spec-superflow-${pkg.version.replaceAll('.', '\\.')}\\.tgz`),
    );
    assert.match(command, /npm install -g "<path>"/);
    assert.match(command, /rerun `\/workflow-init package=<absolute-tgz-path>`/);
    assert.match(command, new RegExp(`spec-superflow-cli-version: ${pkg.version.replaceAll('.', '\\.')}`));
    assert.doesNotMatch(command, /\bsudo\b.*npm install/);
    assert.match(command, /create task artifacts, or start the\s+development workflow/);
  });

  it('keeps plugin setup commands outside the development state machine', () => {
    const agent = read('agents/spec-superflow.agent.md');

    assert.match(agent, /Execute an explicitly selected Plugin command as written/);
    assert.match(agent, /workflow-init[\s\S]*must not route through/);
    assert.match(agent, /inspect the workspace, or create task artifacts/);
  });

  it('keeps a runnable plugin-relative MCP fixture', () => {
    const fixtureRoot = join(ROOT, 'tests', 'fixtures', 'vscode-plugin-mcp');
    const manifest = JSON.parse(
      readFileSync(join(fixtureRoot, '.plugin', 'plugin.json'), 'utf8'),
    );
    const mcp = JSON.parse(readFileSync(join(fixtureRoot, '.mcp.json'), 'utf8'));

    assert.equal(manifest.mcpServers, '.mcp.json');
    assert.deepEqual(mcp.mcpServers['spec-superflow-local'], {
      command: 'node',
      args: ['${PLUGIN_ROOT}/servers/spec-superflow-mcp.mjs'],
      cwd: '${PLUGIN_ROOT}',
    });
    assert.equal(
      existsSync(join(fixtureRoot, 'servers', 'spec-superflow-mcp.mjs')),
      true,
    );
  });

  it('provides an opt-in Spec Superflow agent', () => {
    const agent = read('agents/spec-superflow.agent.md');

    assert.match(agent, /name: Spec Superflow/);
    assert.match(agent, /user-invocable: true/);
    assert.match(agent, /disable-model-invocation: true/);
    assert.match(agent, /Do not run `ssf inject` inside this agent/);
    assert.match(agent, /copilot-instructions\.md` remains owned by the target repository/);
    assert.match(agent, /Do not copy centrally maintained agents, skills, scripts, or templates/);
  });

  it('keeps workflow commands independent of repository-local scripts', () => {
    const agent = read('agents/spec-superflow.agent.md');
    const workflow = read('skills/workflow-start/SKILL.md');

    assert.doesNotMatch(agent, /CLAUDE_PLUGIN_ROOT|plugin cache directory/);
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
      assert.equal(
        existsSync(join(ROOT, 'skills', skill, 'SKILL.md')),
        true,
        `missing central skill: ${skill}`,
      );
    }
  });

  it('uses the global ssf CLI for workflow commands', () => {
    const skills = [
      read('skills/contract-builder/SKILL.md'),
      read('skills/release-archivist/SKILL.md'),
      read('skills/spec-merger/SKILL.md'),
    ];

    for (const skill of skills) {
      assert.doesNotMatch(skill, /node scripts\/spec-superflow\.mjs/);
    }
    assert.match(skills[0], /`ssf state init <change-dir>`/);
    assert.match(skills[0], /`ssf validate <change-dir>`/);
    assert.match(skills[1], /`ssf state transition <change-dir> closing`/);
    assert.match(skills[2], /`ssf sync <change-dir>`/);
  });
});
