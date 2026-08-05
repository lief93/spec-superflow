import assert from 'node:assert/strict';
import { execFileSync, spawnSync } from 'node:child_process';
import {
  cpSync,
  mkdtempSync,
  mkdirSync,
  readFileSync,
  rmSync,
  symlinkSync,
  writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { afterEach, describe, it } from 'node:test';

import {
  proposeMattVendorSync,
  synchronizeMattPlugin,
  treeDigest,
  verifyMattVendor,
} from '../../scripts/lib/matt-plugin-vendor.mjs';

const ROOT = process.cwd();
const PLUGIN_ROOT = join(
  ROOT,
  'extensions',
  'spec-superflow-companion',
  'matt-plugin',
);
const PINNED_COMMIT = '2ab958093e83e0ec752e6c1c5932da465bf23e0c';
const SYNC_SCRIPT = join(ROOT, 'scripts', 'sync-matt-plugin.mjs');
const PINNED_SKILLS = [
  'skills/engineering/ask-matt',
  'skills/engineering/diagnosing-bugs',
  'skills/engineering/grill-with-docs',
  'skills/engineering/triage',
  'skills/engineering/improve-codebase-architecture',
  'skills/engineering/setup-matt-pocock-skills',
  'skills/engineering/tdd',
  'skills/engineering/to-spec',
  'skills/engineering/to-tickets',
  'skills/engineering/wayfinder',
  'skills/engineering/implement',
  'skills/engineering/prototype',
  'skills/engineering/research',
  'skills/engineering/domain-modeling',
  'skills/engineering/codebase-design',
  'skills/engineering/code-review',
  'skills/engineering/resolving-merge-conflicts',
  'skills/productivity/grill-me',
  'skills/productivity/grilling',
  'skills/productivity/handoff',
  'skills/productivity/teach',
  'skills/productivity/writing-great-skills',
];
const workspaces = [];

function workspace(name) {
  const root = mkdtempSync(join(tmpdir(), `matt-plugin-${name}-`));
  workspaces.push(root);
  return root;
}

function write(path, content) {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, content);
}

function createUpstream(root, skills, options = {}) {
  write(
    join(root, '.claude-plugin', 'plugin.json'),
    `${JSON.stringify({
      name: 'mattpocock-skills',
      version: options.version || '2.0.0',
      repository: 'https://github.com/mattpocock/skills',
      license: 'MIT',
      skills: skills.map(skill => `./skills/${skill}`),
    }, null, 2)}\n`,
  );
  write(
    join(root, 'LICENSE'),
    options.license || 'MIT License\n\nCopyright (c) 2026 Matt Pocock\n',
  );
  for (const skill of skills) {
    write(
      join(root, 'skills', skill, 'SKILL.md'),
      `---\nname: ${skill.split('/').at(-1)}\ndescription: Fixture\n---\n\n# Fixture\n`,
    );
  }
  execFileSync('git', ['init', '-q'], { cwd: root });
  execFileSync('git', ['add', '.'], { cwd: root });
  execFileSync(
    'git',
    ['-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture'],
    { cwd: root },
  );
  return execFileSync('git', ['rev-parse', 'HEAD'], { cwd: root, encoding: 'utf8' }).trim();
}

function copyPlugin(name) {
  const root = workspace(name);
  const plugin = join(root, 'matt-plugin');
  cpSync(PLUGIN_ROOT, plugin, { recursive: true });
  return plugin;
}

afterEach(() => {
  for (const root of workspaces.splice(0)) {
    rmSync(root, { recursive: true, force: true });
  }
});

describe('Matt Plugin vendor boundary', () => {
  it('matches the pinned official 22-Skill inventory and all selected resources', () => {
    const result = verifyMattVendor(PLUGIN_ROOT);

    assert.equal(result.provenance.upstream.commit, PINNED_COMMIT);
    assert.equal(result.provenance.upstream.version, '1.2.0');
    assert.equal(result.provenance.selectedSkills.length, 22);
    assert.equal(result.provenance.files.length, 66);
    assert.deepEqual(result.provenance.selectedSkills, PINNED_SKILLS);
    assert.equal(
      result.provenance.selectedSkills.some(path => /in-progress|deprecated|personal|misc/.test(path)),
      false,
    );
  });

  it('audits packaged MIT provenance and rejects any inventory or digest drift', () => {
    const plugin = copyPlugin('tamper');
    const provenance = JSON.parse(readFileSync(join(plugin, 'provenance.json'), 'utf8'));
    assert.match(readFileSync(join(plugin, 'LICENSE'), 'utf8'), /MIT License/);
    assert.equal(verifyMattVendor(plugin).filesDigest, provenance.filesDigest);

    write(join(plugin, provenance.files[0].path), 'tampered\n');
    assert.throws(() => verifyMattVendor(plugin), /digest/i);

    cpSync(PLUGIN_ROOT, plugin, { recursive: true, force: true });
    write(join(plugin, 'skills', 'engineering', 'unselected', 'SKILL.md'), '# extra\n');
    assert.throws(() => verifyMattVendor(plugin), /extra|inventory/i);

    cpSync(PLUGIN_ROOT, plugin, { recursive: true, force: true });
    rmSync(join(plugin, provenance.files[0].path));
    assert.throws(() => verifyMattVendor(plugin), /missing|inventory/i);
  });

  it('proposes every official manifest inventory change for an explicit future commit', () => {
    const source = workspace('future-source');
    const commit = createUpstream(source, [
      'engineering/ask-matt',
      'engineering/new-official-skill',
    ]);

    const proposal = proposeMattVendorSync({
      pluginRoot: PLUGIN_ROOT,
      sourceRoot: source,
      repository: 'https://github.com/mattpocock/skills',
      commit,
    });

    assert.equal(proposal.previousCount, 22);
    assert.equal(proposal.proposedCount, 2);
    assert.deepEqual(proposal.added, ['skills/engineering/new-official-skill']);
    assert.equal(proposal.removed.includes('skills/engineering/diagnosing-bugs'), true);
    assert.deepEqual(proposal.renamed, []);
  });

  it('requires an explicit commit and keeps a local-source dry run read-only', () => {
    for (const args of [[], ['--commit', 'short'], ['--unknown']]) {
      const result = spawnSync(process.execPath, [SYNC_SCRIPT, ...args], {
        cwd: ROOT,
        encoding: 'utf8',
      });
      assert.notEqual(result.status, 0);
    }

    const source = workspace('cli-dry-run-source');
    const commit = createUpstream(source, ['engineering/ask-matt']);
    const before = treeDigest(PLUGIN_ROOT);
    const result = spawnSync(
      process.execPath,
      [SYNC_SCRIPT, '--commit', commit, '--source', source],
      { cwd: ROOT, encoding: 'utf8' },
    );

    assert.equal(result.status, 0, result.stderr || result.stdout);
    const proposal = JSON.parse(result.stdout);
    assert.equal(proposal.applied, false);
    assert.equal(proposal.proposedCommit, commit);
    assert.equal(proposal.previousCount, 22);
    assert.equal(proposal.proposedCount, 1);
    assert.equal(treeDigest(PLUGIN_ROOT), before);
  });

  it('preserves the complete current vendor tree on every unsafe or conflicting sync failure', () => {
    const plugin = copyPlugin('failures');
    const original = treeDigest(plugin);

    write(join(plugin, 'skills', 'engineering', 'ask-matt', 'SKILL.md'), 'local drift\n');
    const drifted = treeDigest(plugin);
    assert.throws(
      () => synchronizeMattPlugin({
        pluginRoot: plugin,
        sourceRoot: workspace('unused-source'),
        repository: 'https://github.com/mattpocock/skills',
        commit: '0'.repeat(40),
      }),
      /local.*drift|digest/i,
    );
    assert.notEqual(drifted, original);
    assert.equal(treeDigest(plugin), drifted);

    cpSync(PLUGIN_ROOT, plugin, { recursive: true, force: true });
    const restored = treeDigest(plugin);
    const traversal = workspace('traversal-source');
    createUpstream(traversal, ['engineering/ask-matt']);
    const manifestPath = join(traversal, '.claude-plugin', 'plugin.json');
    const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'));
    manifest.skills.push('../outside');
    write(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);
    execFileSync('git', ['add', '.'], { cwd: traversal });
    execFileSync(
      'git',
      ['-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'traversal'],
      { cwd: traversal },
    );
    const traversalCommit = execFileSync(
      'git', ['rev-parse', 'HEAD'], { cwd: traversal, encoding: 'utf8' },
    ).trim();
    assert.throws(
      () => proposeMattVendorSync({
        pluginRoot: plugin,
        sourceRoot: traversal,
        repository: 'https://github.com/mattpocock/skills',
        commit: traversalCommit,
      }),
      /path|traversal|commit/i,
    );
    assert.equal(treeDigest(plugin), restored);

    const dirtySource = workspace('dirty-source');
    const dirtyCommit = createUpstream(dirtySource, ['engineering/ask-matt']);
    write(join(dirtySource, 'skills', 'engineering', 'ask-matt', 'SKILL.md'), 'dirty source\n');
    assert.throws(
      () => proposeMattVendorSync({
        pluginRoot: plugin,
        sourceRoot: dirtySource,
        repository: 'https://github.com/mattpocock/skills',
        commit: dirtyCommit,
      }),
      /source.*clean|working tree/i,
    );
    assert.equal(treeDigest(plugin), restored);

    const source = workspace('rollback-source');
    const commit = createUpstream(source, ['engineering/ask-matt']);
    assert.throws(
      () => synchronizeMattPlugin({
        pluginRoot: plugin,
        sourceRoot: source,
        repository: 'https://github.com/mattpocock/skills',
        commit,
        failAfterBackup: true,
      }),
      /injected/i,
    );
    assert.equal(treeDigest(plugin), restored);

    const linkRoot = workspace('link-destination');
    const linkedPlugin = join(linkRoot, 'matt-plugin');
    symlinkSync(plugin, linkedPlugin, 'dir');
    assert.throws(
      () => synchronizeMattPlugin({
        pluginRoot: linkedPlugin,
        sourceRoot: source,
        repository: 'https://github.com/mattpocock/skills',
        commit,
      }),
      /symbolic|destination|canonical/i,
    );
    assert.equal(treeDigest(plugin), restored);
  });
});
