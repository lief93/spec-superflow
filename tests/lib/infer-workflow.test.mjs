// tests/lib/infer-workflow.test.mjs
// Tests for scripts/infer-workflow.mjs — mode inference logic
import { describe, it, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';

let tempDir;

describe('infer-workflow: inferMode()', () => {
  let inferMode;
  let inferCapability;

  before(async () => {
    tempDir = mkdtempSync(join(tmpdir(), 'ssf-infer-'));
    const modulePath = join(process.cwd(), 'scripts/infer-workflow.mjs');
    const mod = await import(modulePath);
    inferMode = mod.inferMode;
    inferCapability = mod.inferCapability;
  });

  after(() => {
    if (tempDir) rmSync(tempDir, { recursive: true, force: true });
  });

  it('returns full mode for empty directory (no artifacts)', () => {
    const result = inferMode(tempDir);
    assert.equal(result.mode, 'full');
    assert.equal(result.explicit, false);
  });

  it('preserves explicit hotfix override for ordinary non-migration changes', () => {
    writeFileSync(join(tempDir, '.spec-superflow.yaml'), 'state: executing\nworkflow: hotfix');
    const result = inferMode(tempDir);
    assert.equal(result.mode, 'hotfix');
    assert.equal(result.explicit, true);
  });

  it('preserves explicit tweak override', () => {
    writeFileSync(join(tempDir, '.spec-superflow.yaml'), 'state: executing\nworkflow: tweak');
    const result = inferMode(tempDir);
    assert.equal(result.mode, 'tweak');
    assert.equal(result.explicit, true);
  });

  it('infers hotfix for small change (≤2 tasks, ≤2 files, no code files in tasks)', () => {
    // Use consistent paths — same file names in proposal AND tasks to avoid unique-count inflation
    writeFileSync(join(tempDir, '.spec-superflow.yaml'), 'state: exploring\nworkflow: auto');
    writeFileSync(join(tempDir, 'proposal.md'), '# Proposal\nFix typo in README.md');
    writeFileSync(join(tempDir, 'tasks.md'), '- [ ] Fix typo in README.md\n- [ ] Verify fix');

    const result = inferMode(tempDir);
    // Hotfix check runs before tweak; 2 tasks, 1 file, no keywords → hotfix wins
    assert.equal(result.mode, 'hotfix', `Expected hotfix but got ${result.mode}: ${result.reason}`);
  });

  it('infers hotfix for small code change (≤2 tasks, ≤2 files, no schema)', () => {
    writeFileSync(join(tempDir, '.spec-superflow.yaml'), 'state: exploring\nworkflow: auto');
    writeFileSync(join(tempDir, 'proposal.md'), '# Proposal\nFix null check in util.ts');
    writeFileSync(join(tempDir, 'tasks.md'), '- [ ] Add null check in util.ts\n- [ ] Add test for null case');

    const result = inferMode(tempDir);
    // 2 tasks, 1 file (util.ts), no schema keyword, code file → hotfix
    assert.equal(result.mode, 'hotfix', `Expected hotfix but got ${result.mode}: ${result.reason}`);
  });

  it('infers tweak for config/doc-only change (≤4 tasks)', () => {
    writeFileSync(join(tempDir, '.spec-superflow.yaml'), 'state: exploring\nworkflow: auto');
    writeFileSync(join(tempDir, 'proposal.md'), '# Proposal\nUpdate README.md');
    writeFileSync(join(tempDir, 'tasks.md'), '- [ ] Update README.md\n- [ ] Update CHANGELOG.md\n- [ ] Update version in package.json');

    const result = inferMode(tempDir);
    // 3 tasks, only doc/config files → tweak
    assert.equal(result.mode, 'tweak', `Expected tweak but got ${result.mode}: ${result.reason}`);
  });

  it('infers full when schema keyword detected', () => {
    writeFileSync(join(tempDir, '.spec-superflow.yaml'), 'state: exploring\nworkflow: auto');
    writeFileSync(join(tempDir, 'proposal.md'), '# Proposal\nChange the API interface for src/auth.ts');
    writeFileSync(join(tempDir, 'tasks.md'), '- [ ] Update API\n- [ ] Update tests');

    const result = inferMode(tempDir);
    assert.equal(result.mode, 'full');
    assert.ok(result.reason.includes('schema/API'));
  });

  it('infers full when new module keyword detected', () => {
    writeFileSync(join(tempDir, '.spec-superflow.yaml'), 'state: exploring\nworkflow: auto');
    writeFileSync(join(tempDir, 'proposal.md'), '# Proposal\nAdd 新增模块 for payment processing');
    writeFileSync(join(tempDir, 'tasks.md'), '- [ ] Create new module');

    const result = inferMode(tempDir);
    assert.equal(result.mode, 'full');
    assert.ok(result.reason.includes('new module'));
  });

  it('infers full when too many files (> 2) for hotfix', () => {
    writeFileSync(join(tempDir, '.spec-superflow.yaml'), 'state: exploring\nworkflow: auto');
    writeFileSync(join(tempDir, 'proposal.md'), '# Big change\nModify src/a.ts src/b.ts src/c.ts');
    writeFileSync(join(tempDir, 'tasks.md'), '- [ ] Task 1\n- [ ] Task 2\n- [ ] Task 3');

    const result = inferMode(tempDir);
    // 3 files > 2 → not hotfix; 3 tasks ≤ 4 but files contain code → not tweak → full
    assert.equal(result.mode, 'full');
  });

  it('infers full when too many tasks (> 2) for hotfix (but not tweak due to code files)', () => {
    writeFileSync(join(tempDir, '.spec-superflow.yaml'), 'state: exploring\nworkflow: auto');
    writeFileSync(join(tempDir, 'proposal.md'), '# Change\nModify src/a.ts');
    writeFileSync(join(tempDir, 'tasks.md'), '- [ ] Task 1\n- [ ] Task 2\n- [ ] Task 3\n- [ ] Task 4\n- [ ] Task 5');

    const result = inferMode(tempDir);
    assert.equal(result.mode, 'full');
  });

  it('returns reason string for all modes', () => {
    const result = inferMode(tempDir);
    assert.ok(typeof result.reason === 'string');
    assert.ok(result.reason.length > 0);
  });

  it('detects Android to Harmony migration as a scoped optional capability', () => {
    writeFileSync(join(tempDir, '.spec-superflow.yaml'), 'state: exploring\nworkflow: auto');
    writeFileSync(join(tempDir, 'proposal.md'), '# Proposal\n把 Android Jetpack Compose 项目迁移到鸿蒙 HarmonyOS。');
    writeFileSync(join(tempDir, 'tasks.md'), '- [ ] Convert Compose screens to ArkUI\n- [ ] Build Harmony HAP');

    const capability = inferCapability(tempDir);
    const mode = inferMode(tempDir);

    assert.equal(capability.capability, 'android-to-harmony');
    assert.equal(capability.explicit, false);
    assert.equal(mode.capability, 'android-to-harmony');
    assert.equal(mode.mode, 'full');
    assert.match(mode.reason, /migration-scoped gates/);
  });

  it('detects Android to Harmony migration from DP-0 decisions before planning artifacts exist', () => {
    const changeDir = mkdtempSync(join(tmpdir(), 'ssf-infer-dp0-'));
    try {
      writeFileSync(
        join(changeDir, '.spec-superflow.yaml'),
        'state: exploring\nworkflow: auto\ndp_0_decisions: Migrate Android Jetpack Compose app to HarmonyOS ArkUI',
      );

      const capability = inferCapability(changeDir);
      const mode = inferMode(changeDir);

      assert.equal(capability.capability, 'android-to-harmony');
      assert.equal(mode.capability, 'android-to-harmony');
      assert.equal(mode.mode, 'full');
    } finally {
      rmSync(changeDir, { recursive: true, force: true });
    }
  });

  it('forces an explicit hotfix migration onto the full workflow', () => {
    const changeDir = mkdtempSync(join(tmpdir(), 'ssf-infer-migration-hotfix-'));
    try {
      writeFileSync(
        join(changeDir, '.spec-superflow.yaml'),
        'state: exploring\nworkflow: hotfix\ndp_0_decisions: Port Android Compose app to HarmonyOS ArkUI',
      );

      const mode = inferMode(changeDir);

      assert.equal(mode.capability, 'android-to-harmony');
      assert.equal(mode.mode, 'full');
      assert.match(mode.reason, /migration-scoped gates/);
    } finally {
      rmSync(changeDir, { recursive: true, force: true });
    }
  });

  it('does not enable Android to Harmony capability for ordinary Android work', () => {
    writeFileSync(join(tempDir, '.spec-superflow.yaml'), 'state: exploring\nworkflow: auto');
    writeFileSync(join(tempDir, 'proposal.md'), '# Proposal\nFix Android Compose login validation.');
    writeFileSync(join(tempDir, 'tasks.md'), '- [ ] Update LoginScreen.kt');

    const capability = inferCapability(tempDir);

    assert.equal(capability.capability, null);
  });

  it('does not enable Android to Harmony capability for ordinary Harmony work', () => {
    writeFileSync(join(tempDir, '.spec-superflow.yaml'), 'state: exploring\nworkflow: auto');
    writeFileSync(join(tempDir, 'proposal.md'), '# Proposal\nAdd a HarmonyOS ArkUI settings page.');
    writeFileSync(join(tempDir, 'tasks.md'), '- [ ] Update SettingsPage.ets');

    const capability = inferCapability(tempDir);

    assert.equal(capability.capability, null);
  });

  it('preserves explicit capability override', () => {
    writeFileSync(
      join(tempDir, '.spec-superflow.yaml'),
      'state: exploring\nworkflow: auto\ncapability: android-to-harmony',
    );
    writeFileSync(join(tempDir, 'proposal.md'), '# Proposal\nMigrate the app.');
    writeFileSync(join(tempDir, 'tasks.md'), '- [ ] Plan migration');

    const capability = inferCapability(tempDir);

    assert.equal(capability.capability, 'android-to-harmony');
    assert.equal(capability.explicit, true);
  });
});
