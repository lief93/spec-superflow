// tests/lib/cmd-install-workbuddy.test.mjs
// Tests for scripts/lib/cmd-install-workbuddy.mjs
import { describe, it, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';

let tempDir;
let planInstall, installWorkBuddy;

describe('cmd-install-workbuddy', () => {
  beforeEach(async () => {
    tempDir = mkdtempSync(join(tmpdir(), 'ssf-workbuddy-'));
    const mod = await import(join(process.cwd(), 'scripts/lib/cmd-install-workbuddy.mjs'));
    planInstall = mod.planInstall;
    installWorkBuddy = mod.installWorkBuddy;
  });

  afterEach(() => {
    if (tempDir) rmSync(tempDir, { recursive: true, force: true });
  });

  function makePluginRoot() {
    const pluginRoot = join(tempDir, 'spec-superflow');
    const skillsDir = join(pluginRoot, 'skills');
    mkdirSync(join(skillsDir, 'workflow-start'), { recursive: true });
    mkdirSync(join(skillsDir, 'need-explorer'), { recursive: true });
    writeFileSync(join(skillsDir, 'workflow-start', 'SKILL.md'), '---\nname: workflow-start\n---\n');
    writeFileSync(join(skillsDir, 'need-explorer', 'SKILL.md'), '---\nname: need-explorer\n---\n');
    return pluginRoot;
  }

  it('plans WorkBuddy marketplace paths and enabled plugin keys', () => {
    const pluginRoot = makePluginRoot();
    const plan = planInstall({
      pluginRoot,
      homeDir: join(tempDir, 'home'),
      marketplaceName: 'cb_teams_marketplace',
    });

    assert.deepEqual(plan.skillNames, ['need-explorer', 'workflow-start']);
    assert.equal(
      plan.pluginsDir,
      join(tempDir, 'home', '.workbuddy', 'plugins', 'marketplaces', 'cb_teams_marketplace', 'plugins'),
    );
    assert.deepEqual(plan.enabledPluginKeys, [
      'need-explorer@cb_teams_marketplace',
      'workflow-start@cb_teams_marketplace',
    ]);
  });

  it('copies skills and preserves existing enabledPlugins settings', () => {
    const pluginRoot = makePluginRoot();
    const homeDir = join(tempDir, 'home');
    const settingsDir = join(homeDir, '.workbuddy');
    mkdirSync(settingsDir, { recursive: true });
    writeFileSync(
      join(settingsDir, 'settings.json'),
      JSON.stringify({ enabledPlugins: { 'existing@codebuddy-plugins-official': true } }, null, 2),
    );

    const result = installWorkBuddy({ pluginRoot, homeDir, marketplaceName: 'cb_teams_marketplace' });
    assert.equal(result.skillNames.length, 2);

    const settings = JSON.parse(readFileSync(join(settingsDir, 'settings.json'), 'utf-8'));
    assert.equal(settings.enabledPlugins['existing@codebuddy-plugins-official'], true);
    assert.equal(settings.enabledPlugins['workflow-start@cb_teams_marketplace'], true);
    assert.equal(settings.enabledPlugins['need-explorer@cb_teams_marketplace'], true);
    assert.match(
      readFileSync(
        join(homeDir, '.workbuddy', 'plugins', 'marketplaces', 'cb_teams_marketplace', 'plugins', 'workflow-start', 'SKILL.md'),
        'utf-8',
      ),
      /workflow-start/,
    );
  });

  it('uses the package root by default instead of the caller cwd', () => {
    const previousCwd = process.cwd();
    process.chdir(tempDir);
    try {
      const plan = planInstall({ homeDir: join(tempDir, 'home') });
      assert.equal(plan.skillNames.length, 9);
      assert.ok(plan.skillsDir.endsWith('spec-superflow/skills'));
    } finally {
      process.chdir(previousCwd);
    }
  });
});
