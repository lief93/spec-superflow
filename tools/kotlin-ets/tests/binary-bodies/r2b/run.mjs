// Requires the focused compiler slot. Tests existing production before any fix.
import assert from 'node:assert/strict';
import { mkdirSync, readdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { boundaries, expected, layouts } from './cases.mjs';
import { compiler, core, target, harness, here, identities, root, hash } from './support.mjs';

const { work, run } = harness();
const cp = run('classpath', 'bash', [compiler, '--classpath']).trim();
const production = identities([...core, ...target]);
writeFileSync(join(work, 'identity.json'), JSON.stringify(production, null, 2));
const producerSources = ['Direct.kt', 'Entry.kt', 'Helper.kt'].map(name => join(here, name));
run('combined-build', 'bash', [compiler, '-Xserialize-ir=inline', ...producerSources, '-d', join(work, 'combined.jar')]);
const evidence = join(work, 'evidence.jar');
run('evidence-build', 'bash', [compiler, ...core, ...target, join(here, 'Evidence.kt'), '-d', evidence]);
function inspect(name, jars, source = 'Application.kt', mode) {
  const directory = join(work, name);
  mkdirSync(directory);
  console.log(run(name, 'java', ['-cp', `${cp}:${evidence}`, 'dev.ets.r2b.EvidenceKt',
    [cp, ...jars.map(jar => join(work, jar))].join(':'), join(here, source), directory, ...(mode ? [mode] : [])]).trim());
}
for (const [name, jars] of layouts) {
  if (name === 'second-jar') {
    run('helper-build', 'bash', [compiler, '-Xserialize-ir=inline', join(here, 'Helper.kt'), '-d', join(work, 'helper.jar')]);
    run('entry-build', 'bash', [compiler, '-classpath', `${cp}:${join(work, 'helper.jar')}`, '-Xserialize-ir=inline',
      join(here, 'Direct.kt'), join(here, 'Entry.kt'), '-d', join(work, 'entry.jar')]);
  }
  const classpath = [cp, ...jars.map(jar => join(work, jar))].join(':');
  const oracle = join(work, `${name}-oracle.jar`);
  run(`${name}-oracle-build`, 'bash', [compiler, '-classpath', classpath, join(here, 'Application.kt'), join(here, 'Oracle.kt'), '-d', oracle]);
  assert.deepEqual(run(`${name}-jvm`, 'java', ['-cp', `${classpath}:${oracle}`, 'extensionconsumer.OracleKt']).trim().split('\n'), expected);
  inspect(`${name}-evidence`, jars);
}
run('signature-build', 'bash', [compiler, ...producerSources, '-d', join(work, 'signature.jar')]);
run('signature-helper-build', 'bash', [compiler, join(here, 'Helper.kt'), '-d', join(work, 'signature-helper.jar')]);
for (const name of ['Reified', 'Member', 'Constructor', 'Multifile']) {
  run(`${name}-build`, 'bash', [compiler, '-Xserialize-ir=inline', join(here, `${name}.kt`), '-d', join(work, `${name}.jar`)]);
}
const strip = join(work, 'strip.jar');
run('strip-build', 'bash', [compiler, join(here, '../StripSource.kt'), '-d', strip]);
run('strip-source', 'java', ['-cp', `${cp}:${strip}`, 'binarytest.StripSourceKt', join(work, 'helper.jar'), join(work, 'no-source-helper.jar')]);
for (const [name, jars, source, mode] of boundaries) inspect(`${name}-evidence`, jars, source, mode);
assert.ok(production.every(item => hash(item.path) === item.sha256), 'Focused production changed during baseline');
writeFileSync(join(work, 'producers.json'), JSON.stringify(identities([
  ...readdirSync(work).filter(name => name.endsWith('.jar')).map(name => join(work, name)),
  ...readdirSync(here).filter(name => /\.(kt|mjs)$/.test(name)).map(name => join(here, name)),
]), null, 2));
writeFileSync(join(work, 'complete.json'), JSON.stringify({ layouts: layouts.length, jvmCases: 6, inlineBlocksPerLayout: 8,
  boundaries: boundaries.length, productionUnchanged: true }));
console.log('PASS focused existing-production extension baseline; no public CLI/target execution in this mode');
