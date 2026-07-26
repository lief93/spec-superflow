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
    const manifest = JSON.parse(read('plugin.json'));

    assert.equal(manifest.skills, 'skills/');
    assert.equal(manifest.agents, 'agents/');
    assert.equal(manifest.mcpServers, '.mcp.json');
    assert.deepEqual(JSON.parse(read('.mcp.json')), { mcpServers: {} });
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
