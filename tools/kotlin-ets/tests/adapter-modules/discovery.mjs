import assert from 'node:assert/strict';
import { mkdirSync, mkdtempSync, readFileSync, symlinkSync, writeFileSync } from 'node:fs';
import { dirname, delimiter, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { discoverAdapterModules, parseProviders, servicePath } from '../../adapter-modules.mjs';

const here = dirname(fileURLToPath(import.meta.url));
mkdirSync(join(here, '.work'), { recursive: true });
const work = mkdtempSync(join(here, '.work/discovery-'));
const root = join(work, 'tool'), external = join(work, 'external modules');
mkdirSync(root); mkdirSync(external);
const checks = [];
function check(name, action) { action(); checks.push(name); }
function module(path, providers, source = true) {
  mkdirSync(join(path, 'META-INF/services'), { recursive: true });
  writeFileSync(join(path, servicePath), providers);
  if (source) { mkdirSync(join(path, 'src'), { recursive: true }); writeFileSync(join(path, 'src/Provider.kt'), '// discovery does not parse Kotlin classes\n'); }
}
check('No modules preserves an empty registry', () => assert.deepEqual(discoverAdapterModules(root, '').providers, []));
module(join(root, 'adapters/z-last'), 'sample.Z\n# comment\nsample.Z\n');
module(join(external, 'a first'), 'sample.A # inline\r\nsample.B\r');
check('Standard comments, duplicates and CRLF merge deterministically', () => {
  const result = discoverAdapterModules(root, external);
  assert.deepEqual(result.providers, ['sample.A', 'sample.B', 'sample.Z']);
  assert.equal(result.sources.length, 2);
  assert.ok(result.sources.some(path => path.includes('external modules/a first')));
});
check('Root may point directly to an independent module', () =>
  assert.deepEqual(discoverAdapterModules(root, join(external, 'a first')).providers, ['sample.A', 'sample.B', 'sample.Z']));
check('Repeated root and canonical aliases are deduplicated', () => {
  const alias = join(work, 'alias'); symlinkSync(external, alias);
  assert.equal(discoverAdapterModules(root, [external, alias, external].join(delimiter)).modules.length, 2);
});
const another = join(work, 'another'); module(join(another, 'module'), 'sample.C\n');
check('Environment order cannot change merge order', () => assert.deepEqual(
  discoverAdapterModules(root, [external, another].join(delimiter)),
  discoverAdapterModules(root, [another, external].join(delimiter))));
check('Missing requested root fails', () => assert.throws(() => discoverAdapterModules(root, join(work, 'absent')), /not a directory/));
check('File requested as root fails', () => assert.throws(() => discoverAdapterModules(root, join(external, 'a first', servicePath)), /not a directory/));
check('Empty path segment fails', () => assert.throws(() => discoverAdapterModules(root, external + delimiter), /empty root/));
const missing = join(work, 'missing'); mkdirSync(join(missing, 'module'), { recursive: true });
check('Module without descriptor fails', () => assert.throws(() => discoverAdapterModules(root, missing), /Missing adapter SPI descriptor/));
const empty = join(work, 'empty'); module(empty, '# no providers\n');
check('Empty descriptor fails', () => assert.throws(() => discoverAdapterModules(root, empty), /No SPI providers/));
const noSource = join(work, 'no source'); module(noSource, 'sample.Empty', false);
check('Provider without Kotlin sources fails', () => assert.throws(() => discoverAdapterModules(root, noSource), /no Kotlin sources/));
check('Malformed provider names retain line diagnostics', () => {
  for (const name of ['sample..Bad', 'bad/name', 'sample.Bad other', '7Bad', 'sample.Bad;'])
    assert.throws(() => parseProviders('# comment\n' + name, 'service'), /service:2/);
});
check('Ordinary nested and Unicode Java provider names are accepted', () =>
  assert.deepEqual(parseProviders('sample.Outer$Provider\nsample.Éclair\n', 'service'), ['sample.Outer$Provider', 'sample.Éclair']));
const cycle = join(work, 'cycle'); module(cycle, 'sample.Cycle'); symlinkSync(cycle, join(cycle, 'src/loop'));
check('Cyclic source directories fail', () => assert.throws(() => discoverAdapterModules(root, cycle), /Cyclic adapter source/));
check('Build CLI writes a standard SPI resource and NUL-delimited paths', () => {
  const build = join(work, 'build'); mkdirSync(build);
  const result = spawnSync(process.execPath, [resolve(here, '../../adapter-modules.mjs'), root, build], {
    env: { ...process.env, KOTLIN_ETS_ADAPTER_DIRS: external }, encoding: 'utf8',
  });
  assert.equal(result.status, 0, result.stderr);
  assert.equal(readFileSync(join(build, 'spi', servicePath), 'utf8'), 'sample.A\nsample.B\nsample.Z\n');
  assert.deepEqual(readFileSync(join(build, 'adapter-sources.list'), 'utf8').split('\0').filter(Boolean), discoverAdapterModules(root, external).sources);
});
writeFileSync(join(work, 'result.json'), JSON.stringify({ work, checks, passed: true }, null, 2));
console.log(`PASS ${checks.length} discovery checks; no JVM: ${work}`);
