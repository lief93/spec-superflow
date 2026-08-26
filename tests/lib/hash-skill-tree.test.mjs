import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { cpSync, mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { it } from 'node:test';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const CHANGE_EVIDENCE = join(ROOT, 'changes', 'android-to-harmony-54-benchmark', 'evidence');
const BUNDLED_SKILL_ROOT = join(ROOT, 'skills', 'migrate-android-compose-to-harmony');
const CANONICAL_SKILL_ROOT = process.env.ANDROID_TO_HARMONY_CANONICAL_SKILL_ROOT;
const HASH_SCRIPT = join(ROOT, 'skills', 'migrate-android-compose-to-harmony', 'scripts', 'hash_skill_tree.py');

function readJson(path) {
  return JSON.parse(readFileSync(path, 'utf8'));
}

function hashTree(root, output) {
  const raw = execFileSync(
    'python3',
    [HASH_SCRIPT, '--root', root, '--output', output],
    { encoding: 'utf8' },
  );
  return JSON.parse(raw);
}

it('canonical skill tree manifest is path-independent', () => {
  const temp = mkdtempSync(join(tmpdir(), 'ssf-hash-skill-tree-'));

  try {
    const copiedRoot = join(temp, 'copied-skill');
    cpSync(BUNDLED_SKILL_ROOT, copiedRoot, { recursive: true });

    const bundledOutput = join(temp, 'bundled.json');
    const copiedOutput = join(temp, 'copied.json');
    const bundledResult = hashTree(BUNDLED_SKILL_ROOT, bundledOutput);
    const copiedResult = hashTree(copiedRoot, copiedOutput);
    const evidenceManifest = readJson(join(CHANGE_EVIDENCE, 'bundled-skill-tree-manifest.json'));

    assert.equal(bundledResult.ok, true);
    assert.equal(copiedResult.ok, true);
    assert.equal(bundledResult.file_count, 68);
    assert.equal(copiedResult.file_count, 68);

    const bundledManifest = readJson(bundledOutput);
    const copiedManifest = readJson(copiedOutput);
    assert.equal(bundledManifest.tree_sha256, copiedManifest.tree_sha256);
    assert.equal(bundledManifest.tree_sha256, evidenceManifest.tree_sha256);
    assert.equal(bundledManifest.file_count, evidenceManifest.file_count);
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});

it('digest binding artifact ties vendored skill to the canonical tree hash', () => {
  const temp = mkdtempSync(join(tmpdir(), 'ssf-current-bundled-skill-'));
  const canonicalManifest = readJson(join(CHANGE_EVIDENCE, 'canonical-skill-tree-manifest.json'));
  const bundledManifest = readJson(join(CHANGE_EVIDENCE, 'bundled-skill-tree-manifest.json'));
  const binding = readJson(join(CHANGE_EVIDENCE, 'repo-skill-binding.json'));

  try {
    const currentBundledOutput = join(temp, 'current-bundled.json');
    const currentBundledResult = hashTree(
      join(ROOT, 'skills', 'migrate-android-compose-to-harmony'),
      currentBundledOutput,
    );
    const currentBundledManifest = readJson(currentBundledOutput);

    assert.equal(currentBundledResult.ok, true);
    assert.equal(binding.schema, 'android-to-harmony.repo-skill-binding.v1');
    assert.equal(binding.bundled_skill_path, 'skills/migrate-android-compose-to-harmony');
    assert.equal(binding.file_count, 68);
    assert.equal(binding.digests_match, true);
    assert.equal(binding.canonical_tree_sha256, canonicalManifest.tree_sha256);
    assert.equal(binding.bundled_tree_sha256, bundledManifest.tree_sha256);
    assert.equal(binding.bundled_tree_sha256, currentBundledManifest.tree_sha256);
    assert.equal(binding.canonical_tree_sha256, 'bb220e2b7bb4ea8b4626f351e51e2dca23e9784059ccd8b1d87d6016957459f1');
    assert.equal(bundledManifest.local_root.endsWith('skills/migrate-android-compose-to-harmony'), true);
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});

it('optional canonical cache comparison is skipped unless explicitly configured', () => {
  if (!CANONICAL_SKILL_ROOT) {
    return;
  }

  const temp = mkdtempSync(join(tmpdir(), 'ssf-canonical-skill-tree-'));
  try {
    const canonicalOutput = join(temp, 'canonical.json');
    const bundledOutput = join(temp, 'bundled.json');
    const canonicalResult = hashTree(CANONICAL_SKILL_ROOT, canonicalOutput);
    const bundledResult = hashTree(BUNDLED_SKILL_ROOT, bundledOutput);

    assert.equal(canonicalResult.ok, true);
    assert.equal(bundledResult.ok, true);
    assert.equal(
      readJson(canonicalOutput).tree_sha256,
      readJson(bundledOutput).tree_sha256,
    );
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});
