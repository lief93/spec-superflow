import { execFileSync, spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import {
  appendFileSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { verifyOfflineBundleIntegrity } from '../../scripts/lib/offline-bundle-integrity.mjs';

const ROOT = process.cwd();
const VERSION = '0.14.0';
const EXPECTED = {
  name: 'spec-superflow',
  version: VERSION,
  node: '>=22',
};
const tempRoots = [];

function sha256(filePath) {
  return createHash('sha256').update(readFileSync(filePath)).digest('hex');
}

function writeBundle({ forbiddenEntry = false } = {}) {
  const root = mkdtempSync(join(tmpdir(), 'ssf-integrity-test-'));
  tempRoots.push(root);
  const bundleDir = join(root, 'bundle');
  const archiveRoot = join(root, 'archive');
  const packageRoot = join(archiveRoot, 'package');
  const filename = `spec-superflow-${VERSION}.tgz`;
  const packagePath = join(bundleDir, filename);

  mkdirSync(bundleDir);
  mkdirSync(packageRoot, { recursive: true });
  writeFileSync(join(packageRoot, 'package.json'), JSON.stringify({
    name: EXPECTED.name,
    version: VERSION,
    engines: { node: EXPECTED.node },
  }));
  if (forbiddenEntry) {
    mkdirSync(join(packageRoot, 'docs'), { recursive: true });
    writeFileSync(join(packageRoot, 'docs', '.!25091!.DS_Store'), '');
  }
  execFileSync('tar', ['-czf', packagePath, '-C', archiveRoot, 'package']);
  const digest = sha256(packagePath);
  writeFileSync(join(bundleDir, 'manifest.json'), `${JSON.stringify({
    name: EXPECTED.name,
    version: VERSION,
    node: EXPECTED.node,
    package: filename,
    sha256: digest,
    pluginPathAfterExtraction: 'package/',
  }, null, 2)}\n`);
  writeFileSync(join(bundleDir, 'SHA256SUMS'), `${digest}  ${filename}\n`);
  return { bundleDir, filename, packagePath };
}

function mutateManifest(bundleDir, mutate) {
  const path = join(bundleDir, 'manifest.json');
  const manifest = JSON.parse(readFileSync(path, 'utf8'));
  mutate(manifest);
  writeFileSync(path, `${JSON.stringify(manifest, null, 2)}\n`);
}

function rewriteDigestSidecars(bundleDir, filename, digest) {
  mutateManifest(bundleDir, (manifest) => {
    manifest.sha256 = digest;
  });
  writeFileSync(join(bundleDir, 'SHA256SUMS'), `${digest}  ${filename}\n`);
}

afterEach(() => {
  for (const root of tempRoots.splice(0)) {
    rmSync(root, { recursive: true, force: true });
  }
});

describe('offline bundle integrity gate', () => {
  it('accepts a consistent manifest checksum and readable archive', () => {
    const { bundleDir, packagePath } = writeBundle();

    const result = verifyOfflineBundleIntegrity(bundleDir, EXPECTED);

    assert.equal(result.packagePath, packagePath);
    assert.ok(result.entries.includes('package/package.json'));
  });

  it('integrity-only CLI exits zero for a valid bundle', () => {
    const { bundleDir } = writeBundle();
    const result = spawnSync(
      process.execPath,
      ['scripts/verify-offline-bundle.mjs', '--bundle', bundleDir, '--integrity-only'],
      { cwd: ROOT, encoding: 'utf8' },
    );

    assert.equal(result.status, 0, result.stderr || result.stdout);
    assert.match(result.stdout, /Integrity: PASS/);
  });

  it('rejects every inconsistent manifest checksum and archive field', () => {
    const cases = [
      ['manifest name', ({ bundleDir }) => mutateManifest(bundleDir, (m) => { m.name = 'other'; })],
      ['manifest version', ({ bundleDir }) => mutateManifest(bundleDir, (m) => { m.version = '0.13.0'; })],
      ['manifest Node requirement', ({ bundleDir }) => mutateManifest(bundleDir, (m) => { m.node = '>=20'; })],
      ['manifest package filename', ({ bundleDir }) => mutateManifest(bundleDir, (m) => { m.package = 'other.tgz'; })],
      ['manifest digest', ({ bundleDir }) => mutateManifest(bundleDir, (m) => { m.sha256 = '0'.repeat(64); })],
      ['checksum filename', ({ bundleDir }) => writeFileSync(
        join(bundleDir, 'SHA256SUMS'),
        `${'0'.repeat(64)}  other.tgz\n`,
      )],
      ['checksum digest', ({ bundleDir, filename }) => writeFileSync(
        join(bundleDir, 'SHA256SUMS'),
        `${'f'.repeat(64)}  ${filename}\n`,
      )],
      ['actual tgz digest', ({ packagePath }) => appendFileSync(packagePath, 'tampered')],
      ['unreadable tgz', ({ bundleDir, filename, packagePath }) => {
        writeFileSync(packagePath, 'not a gzip archive');
        rewriteDigestSidecars(bundleDir, filename, sha256(packagePath));
      }],
    ];

    for (const [name, mutate] of cases) {
      const bundle = writeBundle();
      mutate(bundle);
      assert.throws(
        () => verifyOfflineBundleIntegrity(bundle.bundleDir, EXPECTED),
        undefined,
        name,
      );
    }
  });

  it('integrity-only CLI exits non-zero for every tampered bundle', () => {
    const cases = [
      ({ bundleDir }) => mutateManifest(bundleDir, (m) => { m.name = 'other'; }),
      ({ bundleDir }) => mutateManifest(bundleDir, (m) => { m.version = '0.13.0'; }),
      ({ bundleDir }) => mutateManifest(bundleDir, (m) => { m.node = '>=20'; }),
      ({ bundleDir }) => mutateManifest(bundleDir, (m) => { m.package = 'other.tgz'; }),
      ({ bundleDir }) => mutateManifest(bundleDir, (m) => { m.sha256 = '0'.repeat(64); }),
      ({ bundleDir }) => writeFileSync(
        join(bundleDir, 'SHA256SUMS'),
        `${'0'.repeat(64)}  other.tgz\n`,
      ),
      ({ bundleDir, filename }) => writeFileSync(
        join(bundleDir, 'SHA256SUMS'),
        `${'f'.repeat(64)}  ${filename}\n`,
      ),
      ({ packagePath }) => appendFileSync(packagePath, 'tampered'),
      ({ bundleDir, filename, packagePath }) => {
        writeFileSync(packagePath, 'not a gzip archive');
        rewriteDigestSidecars(bundleDir, filename, sha256(packagePath));
      },
    ];

    for (const mutate of cases) {
      const bundle = writeBundle();
      mutate(bundle);
      const result = spawnSync(
        process.execPath,
        ['scripts/verify-offline-bundle.mjs', '--bundle', bundle.bundleDir, '--integrity-only'],
        { cwd: ROOT, encoding: 'utf8' },
      );
      assert.notEqual(result.status, 0, result.stdout);
    }
  });

  it('npm package excludes system and editor temporary files', () => {
    const [pack] = JSON.parse(execFileSync(
      'npm',
      ['pack', '--dry-run', '--json'],
      { cwd: ROOT, encoding: 'utf8' },
    ));
    const paths = pack.files.map((file) => file.path);
    const forbidden = paths
      .filter((path) => /(^|\/)(?:\.DS_Store|\._[^/]+|\.![^/]*!\.DS_Store)$/.test(path));

    assert.deepEqual(forbidden, []);
    for (const excludedRoot of ['changes/', 'release-assets/', 'tests/', 'validation/']) {
      assert.equal(
        paths.some((path) => path.startsWith(excludedRoot)),
        false,
        `unexpected distribution entry under ${excludedRoot}`,
      );
    }
    for (const required of [
      '.mcp.json',
      '.plugin/plugin.json',
      'agents/spec-superflow.agent.md',
      'commands/workflow-init.md',
    ]) {
      assert.ok(paths.includes(required), `missing required package entry: ${required}`);
    }
  });

  it('rejects forbidden package entries', () => {
    const { bundleDir } = writeBundle({ forbiddenEntry: true });

    assert.throws(
      () => verifyOfflineBundleIntegrity(bundleDir, EXPECTED),
      /forbidden package entry/i,
    );
  });

  it('evidence does not infer VS Code command results', () => {
    const source = readFileSync(join(ROOT, 'scripts/verify-offline-bundle.mjs'), 'utf8');

    assert.doesNotMatch(source, /workflow-init READY result/);
    assert.doesNotMatch(source, /Idempotent second workflow-init/);
    assert.match(source, /Pending VS Code runtime/);
  });
});
