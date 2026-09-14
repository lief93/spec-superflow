// Focused compiler slot required. Public CLI replay is separately gated.
import assert from 'node:assert/strict';
import { mkdirSync, readdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { boundaries, expected, layouts } from './cases.mjs';
import { compiler, core, harness, identities, root, hash } from '../r2b/support.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const { work, run } = harness(join(here, '.work'));
const cp = run('classpath', 'bash', [compiler, '--classpath']).trim();
const production = identities([...core, join(root, 'src/target/Tree.kt')]);
writeFileSync(join(work, 'identity.json'), JSON.stringify(production, null, 2));
const all = ['IntEntry.kt', 'DoubleEntry.kt', 'IntHelper.kt', 'DoubleHelper.kt'];
function build(name, files, serialized = true, dependencies = []) {
  run(`${name}-build`, 'bash', [compiler, ...(serialized ? ['-Xserialize-ir=inline'] : []),
    ...(dependencies.length ? ['-classpath', [cp, ...dependencies.map(jar => join(work, jar))].join(':')] : []),
    ...files.map(file => join(here, file)), '-d', join(work, `${name}.jar`)]);
}
build('combined', all);
build('int', ['IntEntry.kt', 'IntHelper.kt']);
build('double', ['DoubleEntry.kt', 'DoubleHelper.kt']);
const evidence = join(work, 'evidence.jar');
run('evidence-build', 'bash', [compiler, ...core, join(root, 'src/target/Tree.kt'), join(here, 'Evidence.kt'), '-d', evidence]);
function inspect(name, jars, source = 'Application.kt', mode) {
  const directory = join(work, name);
  mkdirSync(directory);
  console.log(run(name, 'java', ['-cp', `${cp}:${evidence}`, 'dev.ets.r2d.EvidenceKt',
    [cp, ...jars.map(jar => join(work, jar))].join(':'), join(here, source), directory, ...(mode ? [mode] : [])]).trim());
}
for (const [name, jars] of layouts) {
  const classpath = [cp, ...jars.map(jar => join(work, jar))].join(':');
  const oracle = join(work, `${name}-oracle.jar`);
  run(`${name}-oracle-build`, 'bash', [compiler, '-classpath', classpath, join(here, 'Application.kt'), join(here, 'Oracle.kt'), '-d', oracle]);
  assert.deepEqual(run(`${name}-jvm`, 'java', ['-cp', `${classpath}:${oracle}`, 'overloadconsumer.OracleKt']).trim().split('\n'), expected);
  inspect(`${name}-evidence`, jars);
}
build('all-helpers', ['IntHelper.kt', 'DoubleHelper.kt']);
build('entries', ['IntEntry.kt', 'DoubleEntry.kt'], true, ['all-helpers.jar']);
build('int-helper', ['IntHelper.kt']);
build('signature-double-helper', ['DoubleHelper.kt'], false);
build('signature-double', ['DoubleEntry.kt', 'DoubleHelper.kt'], false);
for (const [name, jars, mode] of boundaries) inspect(`${name}-evidence`, jars, 'SelectedDouble.kt', mode);
assert.ok(production.every(item => hash(item.path) === item.sha256), 'Focused production changed during baseline');
writeFileSync(join(work, 'producers.json'), JSON.stringify(identities([
  ...readdirSync(work).filter(name => name.endsWith('.jar')).map(name => join(work, name)),
  ...readdirSync(here).filter(name => /\.(kt|mjs)$/.test(name)).map(name => join(here, name)),
  join(here, '../r2b/support.mjs'),
]), null, 2));
writeFileSync(join(work, 'complete.json'), JSON.stringify({ layouts: 3, jvmCases: 9, officialSignatures: 4,
  inlineBlocksPerLayout: 8, selectedOverloadBoundaries: 3, productionUnchanged: true }));
console.log('PASS focused official overload selection; no target-type or same-name fallback');
