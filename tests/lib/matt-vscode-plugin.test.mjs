import assert from 'node:assert/strict';
import { existsSync, mkdtempSync, readFileSync, readdirSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';
import { afterEach, describe, it } from 'node:test';

const ROOT = process.cwd();
const SOURCE = join(ROOT, 'extensions', 'spec-superflow-companion', 'matt-plugin');
const workspaces = [];

function read(path) {
  return readFileSync(path, 'utf8');
}

function stage() {
  const root = mkdtempSync(join(tmpdir(), 'matt-vscode-plugin-'));
  workspaces.push(root);
  const result = spawnSync(
    process.execPath,
    [join(ROOT, 'scripts', 'build-vscode-vsix.mjs'), '--stage-only', root],
    { cwd: ROOT, encoding: 'utf8' },
  );
  assert.equal(result.status, 0, result.stderr || result.stdout);
  return join(root, 'extension');
}

function discoverSkillPathsLikeVsCode(pluginRoot, configuredPaths) {
  const paths = Array.isArray(configuredPaths) ? configuredPaths : [configuredPaths];
  const discovered = [];

  for (const configuredPath of paths) {
    const root = join(pluginRoot, configuredPath);
    if (existsSync(join(root, 'SKILL.md'))) {
      discovered.push(configuredPath.replace(/\/$/, ''));
      continue;
    }
    if (!existsSync(root)) continue;

    for (const entry of readdirSync(root, { withFileTypes: true })) {
      if (entry.isDirectory() && existsSync(join(root, entry.name, 'SKILL.md'))) {
        discovered.push(join(configuredPath, entry.name));
      }
    }
  }

  return discovered.sort();
}

afterEach(() => {
  for (const root of workspaces.splice(0)) rmSync(root, { recursive: true, force: true });
});

describe('Matt Engineering VS Code Plugin', () => {
  it('exposes all selected Skills through VS Code one-level Plugin discovery', () => {
    const extension = stage();
    const pluginRoot = join(extension, 'matt-plugin');
    const manifest = JSON.parse(read(join(pluginRoot, 'plugin.json')));
    const compatibility = JSON.parse(read(join(pluginRoot, 'compatibility.json')));
    const expectedPaths = compatibility.skills.map(skill => skill.path).sort();

    assert.equal(expectedPaths.length, 22);
    assert.deepEqual(discoverSkillPathsLikeVsCode(pluginRoot, manifest.skills), expectedPaths);
  });

  it('registers Ask Matt as an unprefixed user route without Spec workflow ownership', () => {
    const extension = stage();
    const sourceAgent = read(join(SOURCE, 'agents', 'matt-engineering.agent.md'));
    const stagedAgent = read(join(extension, 'matt-plugin', 'agents', 'matt-engineering.agent.md'));
    const manifest = JSON.parse(read(join(extension, 'matt-plugin', 'plugin.json')));
    const provenance = JSON.parse(read(join(extension, 'matt-plugin', 'provenance.json')));

    assert.equal(manifest.name, 'matt-engineering');
    assert.equal(provenance.selectedSkills.length, 22);
    assert.equal(sourceAgent, stagedAgent);
    assert.match(sourceAgent, /name:\s*Matt Engineering/);
    assert.match(sourceAgent, /user-invocable:\s*true/);
    assert.match(sourceAgent, /ask-matt\/SKILL\.md/);
    assert.doesNotMatch(sourceAgent, /matt-ask-matt|spec-superflow|\/workflow-init|\bssf\b|changes\//i);
    for (const skill of provenance.selectedSkills) {
      assert.match(sourceAgent, new RegExp(skill.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
    }
  });

  it('preserves diagnosing-bugs as a model-invoked feedback-loop Skill', () => {
    const extension = stage();
    const skillRoot = join(extension, 'matt-plugin', 'skills', 'engineering', 'diagnosing-bugs');
    const skill = read(join(skillRoot, 'SKILL.md'));
    const metadata = read(join(skillRoot, 'agents', 'openai.yaml'));
    const agent = read(join(extension, 'matt-plugin', 'agents', 'matt-engineering.agent.md'));

    assert.equal(/^disable-model-invocation:\s*true$/m.test(skill), false);
    assert.match(skill, /Build a feedback loop/i);
    assert.match(skill, /red-capable/i);
    assert.match(metadata, /display_name:\s*"Diagnosing Bugs"/);
    assert.match(agent, /diagnosing-bugs\/SKILL\.md/);
    assert.match(
      agent,
      /Before any analysis, response, file read, terminal command, or other tool\s+call[\s\S]*diagnose[\s\S]*debug[\s\S]*broken[\s\S]*failing[\s\S]*slow[\s\S]*load `diagnosing-bugs` first/i,
    );
    assert.doesNotMatch(agent, /spec-superflow|\/workflow-init|\bssf\b|changes\//i);
  });

  it('keeps both grill-me names unprefixed and marks host resolution PENDING', () => {
    const extension = stage();
    const mattRoot = join(extension, 'matt-plugin');
    const compatibility = JSON.parse(read(join(mattRoot, 'compatibility.json')));
    const agent = read(join(mattRoot, 'agents', 'matt-engineering.agent.md'));

    assert.equal(existsSync(join(extension, 'agent-plugin', 'skills', 'grill-me', 'SKILL.md')), true);
    assert.equal(existsSync(join(mattRoot, 'skills', 'productivity', 'grill-me', 'SKILL.md')), true);
    assert.doesNotMatch(agent, /matt-grill-me|exclusive|resolver/i);
    assert.deepEqual(compatibility.duplicateNames, [{
      name: 'grill-me',
      status: 'PENDING',
      reason: 'VS Code host resolution has not been executed for the duplicate name.',
    }]);
  });

  it('keeps every unexecuted Skill PENDING in the compatibility ledger', () => {
    const compatibility = JSON.parse(read(join(SOURCE, 'compatibility.json')));
    const byName = new Map(compatibility.skills.map(entry => [entry.name, entry]));

    assert.equal(compatibility.skills.length, 22);
    for (const name of ['code-review', 'research', 'wayfinder', 'grill-me']) {
      assert.equal(byName.get(name)?.status, 'PENDING');
    }
    assert.equal(compatibility.skills.every(entry => entry.status === 'PENDING'), true);
  });
});
