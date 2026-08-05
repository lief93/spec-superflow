import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import {
  cpSync,
  existsSync,
  lstatSync,
  mkdtempSync,
  mkdirSync,
  readFileSync,
  realpathSync,
  readdirSync,
  renameSync,
  rmSync,
  writeFileSync,
} from 'node:fs';
import { basename, dirname, isAbsolute, join, relative, resolve, sep } from 'node:path';

const MANIFEST_PATH = '.claude-plugin/plugin.json';
const LICENSE_PATH = 'LICENSE';

function sha256(value) {
  return createHash('sha256').update(value).digest('hex');
}

function normalizePath(path) {
  return path.split(sep).join('/').replace(/^\.\//, '');
}

function assertSafeRelative(path, label = 'path') {
  const normalized = normalizePath(path);
  if (
    !normalized
    || isAbsolute(path)
    || normalized === '..'
    || normalized.startsWith('../')
    || normalized.includes('/../')
  ) {
    throw new Error(`Unsafe ${label}: ${path}`);
  }
  return normalized;
}

function assertRegularTree(root) {
  const info = lstatSync(root);
  if (info.isSymbolicLink()) throw new Error(`Symbolic destination is not allowed: ${root}`);
  if (!info.isDirectory()) throw new Error(`Expected directory: ${root}`);
}

function filesUnder(root, base = root) {
  const result = [];
  for (const entry of readdirSync(root, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
    const absolute = join(root, entry.name);
    if (entry.isSymbolicLink()) throw new Error(`Symbolic links are not allowed: ${absolute}`);
    if (entry.isDirectory()) result.push(...filesUnder(absolute, base));
    else if (entry.isFile()) result.push(normalizePath(relative(base, absolute)));
  }
  return result;
}

function fileRecords(root, paths) {
  return [...paths].sort().map(path => {
    const safePath = assertSafeRelative(path, 'inventory path');
    const absolute = join(root, safePath);
    if (!existsSync(absolute)) throw new Error(`Missing inventory file: ${safePath}`);
    if (!lstatSync(absolute).isFile()) throw new Error(`Inventory path is not a file: ${safePath}`);
    return { path: safePath, sha256: sha256(readFileSync(absolute)) };
  });
}

function recordsDigest(records) {
  return sha256(`${JSON.stringify(records)}\n`);
}

function gitCommit(sourceRoot) {
  const result = spawnSync('git', ['rev-parse', 'HEAD'], {
    cwd: sourceRoot,
    encoding: 'utf8',
  });
  if (result.status !== 0) throw new Error(`Cannot resolve source commit: ${result.stderr || result.stdout}`);
  return result.stdout.trim();
}

function assertCleanSource(sourceRoot) {
  const result = spawnSync('git', ['status', '--porcelain', '--untracked-files=all'], {
    cwd: sourceRoot,
    encoding: 'utf8',
  });
  if (result.status !== 0) throw new Error(`Cannot inspect source working tree: ${result.stderr || result.stdout}`);
  if (result.stdout.trim()) throw new Error('Source working tree must be clean.');
}

export function readOfficialManifest(sourceRoot) {
  assertRegularTree(sourceRoot);
  const manifest = JSON.parse(readFileSync(join(sourceRoot, MANIFEST_PATH), 'utf8'));
  if (!Array.isArray(manifest.skills) || manifest.skills.length === 0) {
    throw new Error('Official manifest must select at least one Skill.');
  }
  if (manifest.license !== 'MIT') throw new Error('Official manifest must declare the MIT license.');

  const selectedSkills = manifest.skills.map(path => {
    const safePath = assertSafeRelative(path, 'manifest Skill path');
    if (!safePath.startsWith('skills/')) throw new Error(`Skill path must stay under skills/: ${path}`);
    const absolute = join(sourceRoot, safePath);
    if (!existsSync(absolute) || !lstatSync(absolute).isDirectory()) {
      throw new Error(`Selected Skill directory is missing: ${safePath}`);
    }
    return safePath;
  });
  if (new Set(selectedSkills).size !== selectedSkills.length) {
    throw new Error('Official manifest contains duplicate Skill paths.');
  }
  return { manifest, selectedSkills };
}

export function buildVendorInventory(sourceRoot, selectedSkills) {
  const paths = [];
  for (const skill of selectedSkills) {
    paths.push(...filesUnder(join(sourceRoot, assertSafeRelative(skill)), sourceRoot));
  }
  return fileRecords(sourceRoot, paths);
}

function sourceSnapshot({ sourceRoot, repository, commit }) {
  const actualCommit = gitCommit(sourceRoot);
  if (actualCommit !== commit) {
    throw new Error(`Source commit mismatch: expected ${commit}, got ${actualCommit}`);
  }
  assertCleanSource(sourceRoot);
  const { manifest, selectedSkills } = readOfficialManifest(sourceRoot);
  const license = readFileSync(join(sourceRoot, LICENSE_PATH));
  if (!license.toString('utf8').startsWith('MIT License\n')) {
    throw new Error('Upstream LICENSE is not the expected MIT license text.');
  }
  const files = buildVendorInventory(sourceRoot, selectedSkills);
  return {
    schemaVersion: 1,
    upstream: {
      repository,
      commit,
      version: manifest.version,
      manifestPath: MANIFEST_PATH,
      license: 'MIT',
    },
    selectedSkills,
    files,
    filesDigest: recordsDigest(files),
    licenseSha256: sha256(license),
  };
}

function writeSnapshot(pluginRoot, sourceRoot, provenance) {
  rmSync(join(pluginRoot, 'skills'), { recursive: true, force: true });
  for (const skill of provenance.selectedSkills) {
    cpSync(join(sourceRoot, skill), join(pluginRoot, skill), {
      recursive: true,
      force: true,
      dereference: false,
    });
  }
  cpSync(join(sourceRoot, LICENSE_PATH), join(pluginRoot, LICENSE_PATH));
  const pluginManifestPath = join(pluginRoot, 'plugin.json');
  const pluginManifest = JSON.parse(readFileSync(pluginManifestPath, 'utf8'));
  pluginManifest.skills = provenance.selectedSkills;
  writeFileSync(pluginManifestPath, `${JSON.stringify(pluginManifest, null, 2)}\n`);
  writeFileSync(join(pluginRoot, 'provenance.json'), `${JSON.stringify(provenance, null, 2)}\n`);
}

export function materializeMattVendor({ pluginRoot, sourceRoot, repository, commit }) {
  assertRegularTree(pluginRoot);
  const provenance = sourceSnapshot({ sourceRoot, repository, commit });
  writeSnapshot(pluginRoot, sourceRoot, provenance);
  return verifyMattVendor(pluginRoot);
}

export function verifyMattVendor(pluginRoot) {
  assertRegularTree(pluginRoot);
  const provenance = JSON.parse(readFileSync(join(pluginRoot, 'provenance.json'), 'utf8'));
  const manifest = JSON.parse(readFileSync(join(pluginRoot, 'plugin.json'), 'utf8'));
  if (provenance.schemaVersion !== 1) throw new Error('Unsupported provenance schema.');
  if (provenance.upstream?.license !== 'MIT') throw new Error('Provenance license must be MIT.');
  if (!Array.isArray(provenance.selectedSkills) || !Array.isArray(provenance.files)) {
    throw new Error('Provenance inventory is missing.');
  }
  if (
    manifest.name !== 'matt-engineering'
    || !Array.isArray(manifest.skills)
    || JSON.stringify(manifest.skills) !== JSON.stringify(provenance.selectedSkills)
  ) {
    throw new Error('Matt Plugin manifest Skill paths do not match the provenance inventory.');
  }
  for (const skill of provenance.selectedSkills) {
    const safeSkill = assertSafeRelative(skill, 'selected Skill');
    if (!safeSkill.startsWith('skills/')) throw new Error(`Selected Skill escaped skills/: ${skill}`);
    if (!existsSync(join(pluginRoot, safeSkill, 'SKILL.md'))) {
      throw new Error(`Selected Skill is missing SKILL.md: ${safeSkill}`);
    }
  }
  const expectedByPath = new Map(provenance.files.map(file => [
    assertSafeRelative(file.path, 'provenance path'),
    file,
  ]));
  const expectedPaths = [...expectedByPath.keys()].sort();
  const actualPaths = filesUnder(join(pluginRoot, 'skills'), pluginRoot).sort();
  if (JSON.stringify(actualPaths) !== JSON.stringify(expectedPaths)) {
    throw new Error('Vendor inventory has missing or extra files.');
  }
  const actualRecords = fileRecords(pluginRoot, expectedPaths);
  for (let index = 0; index < actualRecords.length; index += 1) {
    if (actualRecords[index].sha256 !== expectedByPath.get(actualRecords[index].path).sha256) {
      throw new Error(`Vendor digest mismatch: ${actualRecords[index].path}`);
    }
  }
  const filesDigest = recordsDigest(actualRecords);
  if (filesDigest !== provenance.filesDigest) throw new Error('Vendor files digest mismatch.');
  if (sha256(readFileSync(join(pluginRoot, LICENSE_PATH))) !== provenance.licenseSha256) {
    throw new Error('Vendor LICENSE digest mismatch.');
  }
  return { provenance, filesDigest };
}

function skillDigestMap(root, provenance) {
  return new Map(provenance.selectedSkills.map(skill => {
    const records = provenance.files.filter(file => file.path === skill || file.path.startsWith(`${skill}/`));
    return [skill, recordsDigest(records.map(file => ({ ...file, path: file.path.slice(skill.length + 1) })))];
  }));
}

export function proposeMattVendorSync({ pluginRoot, sourceRoot, repository, commit }) {
  const current = verifyMattVendor(pluginRoot).provenance;
  const proposed = sourceSnapshot({ sourceRoot, repository, commit });
  const currentSet = new Set(current.selectedSkills);
  const proposedSet = new Set(proposed.selectedSkills);
  const added = proposed.selectedSkills.filter(skill => !currentSet.has(skill)).sort();
  const removed = current.selectedSkills.filter(skill => !proposedSet.has(skill)).sort();
  const currentDigests = skillDigestMap(pluginRoot, current);
  const proposedDigests = skillDigestMap(sourceRoot, proposed);
  const renamed = [];
  for (const from of removed) {
    const to = added.find(candidate => proposedDigests.get(candidate) === currentDigests.get(from));
    if (to) renamed.push({ from, to });
  }
  return {
    repository,
    commit,
    previousCommit: current.upstream.commit,
    previousCount: current.selectedSkills.length,
    proposedCount: proposed.selectedSkills.length,
    added,
    removed,
    renamed,
    proposed,
  };
}

export function synchronizeMattPlugin({
  pluginRoot,
  sourceRoot,
  repository,
  commit,
  failAfterBackup = false,
}) {
  const requested = resolve(pluginRoot);
  assertRegularTree(requested);
  const resolved = realpathSync(requested);
  if (basename(resolved) !== 'matt-plugin') throw new Error('Destination must be the matt-plugin root.');
  const parent = realpathSync(dirname(resolved));
  if (resolve(parent, basename(resolved)) !== resolved) throw new Error('Destination is not canonical.');

  const proposal = proposeMattVendorSync({ pluginRoot: resolved, sourceRoot, repository, commit });
  const stage = mkdtempSync(join(parent, '.matt-plugin-stage-'));
  const stagedPlugin = join(stage, 'matt-plugin');
  const backup = join(parent, `.matt-plugin-backup-${process.pid}-${Date.now()}`);
  let backedUp = false;
  try {
    cpSync(resolved, stagedPlugin, { recursive: true, dereference: false });
    writeSnapshot(stagedPlugin, sourceRoot, proposal.proposed);
    verifyMattVendor(stagedPlugin);
    renameSync(resolved, backup);
    backedUp = true;
    if (failAfterBackup) throw new Error('Injected failure after backup.');
    renameSync(stagedPlugin, resolved);
    verifyMattVendor(resolved);
    rmSync(backup, { recursive: true, force: true });
    backedUp = false;
    return proposal;
  } catch (error) {
    if (backedUp) {
      rmSync(resolved, { recursive: true, force: true });
      renameSync(backup, resolved);
      backedUp = false;
    }
    throw error;
  } finally {
    rmSync(stage, { recursive: true, force: true });
    if (backedUp) rmSync(backup, { recursive: true, force: true });
  }
}

export function treeDigest(root) {
  assertRegularTree(root);
  const records = fileRecords(root, filesUnder(root));
  return recordsDigest(records);
}
