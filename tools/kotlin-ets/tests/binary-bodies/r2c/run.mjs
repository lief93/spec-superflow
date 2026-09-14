// Focused compiler slot required. No public CLI in this runner.
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
const producerSources = ['Entry.kt', 'Helper.kt'].map(name => join(here, name));
run('combined-build', 'bash', [compiler, '-Xserialize-ir=inline', ...producerSources, '-d', join(work, 'combined.jar')]);
const evidence = join(work, 'evidence.jar');
run('evidence-build', 'bash', [compiler, ...core, join(root, 'src/target/Tree.kt'), join(here, 'Evidence.kt'), '-d', evidence]);
function inspect(name, jars, source = 'Application.kt', mode) {
  const directory = join(work, name);
  mkdirSync(directory);
  console.log(run(name, 'java', ['-cp', `${cp}:${evidence}`, 'dev.ets.r2c.EvidenceKt',
    [cp, ...jars.map(jar => join(work, jar))].join(':'), join(here, source), directory, ...(mode ? [mode] : [])]).trim());
}
for (const [name, jars] of layouts) {
  if (name === 'second-jar') {
    run('helper-build', 'bash', [compiler, '-Xserialize-ir=inline', join(here, 'Helper.kt'), '-d', join(work, 'helper.jar')]);
    run('entry-build', 'bash', [compiler, '-classpath', `${cp}:${join(work, 'helper.jar')}`, '-Xserialize-ir=inline',
      join(here, 'Entry.kt'), '-d', join(work, 'entry.jar')]);
  }
  const classpath = [cp, ...jars.map(jar => join(work, jar))].join(':');
  const oracle = join(work, `${name}-oracle.jar`);
  run(`${name}-oracle-build`, 'bash', [compiler, '-classpath', classpath, join(here, 'Application.kt'), join(here, 'Oracle.kt'), '-d', oracle]);
  assert.deepEqual(run(`${name}-jvm`, 'java', ['-cp', `${classpath}:${oracle}`, 'defaultconsumer.OracleKt']).trim().split('\n'), expected);
  inspect(`${name}-evidence`, jars);
}
// Explicit arguments let the actual JVM consumer run with no helper JAR at all.
const explicitOracle = join(work, 'explicit-oracle.jar');
run('explicit-oracle-build', 'bash', [compiler, '-classpath', `${cp}:${join(work, 'entry.jar')}`,
  join(here, 'ExplicitOnly.kt'), join(here, 'ExplicitOracle.kt'), '-d', explicitOracle]);
assert.deepEqual(run('explicit-jvm-without-helper', 'java', ['-cp', `${cp}:${join(work, 'entry.jar')}:${explicitOracle}`,
  'defaultconsumer.ExplicitOracleKt']).trim().split('\n'), ['11', '8', '-2147483639']);
run('signature-build', 'bash', [compiler, ...producerSources, '-d', join(work, 'signature.jar')]);
run('signature-helper-build', 'bash', [compiler, join(here, 'Helper.kt'), '-d', join(work, 'signature-helper.jar')]);
for (const [name, jars, source, mode] of boundaries) inspect(`${name}-evidence`, jars, source, mode);
assert.ok(production.every(item => hash(item.path) === item.sha256), 'Focused production changed during baseline');
writeFileSync(join(work, 'producers.json'), JSON.stringify(identities([
  ...readdirSync(work).filter(name => name.endsWith('.jar')).map(name => join(work, name)),
  ...readdirSync(here).filter(name => /\.(kt|mjs)$/.test(name)).map(name => join(here, name)),
  join(here, '../r2b/support.mjs'),
]), null, 2));
writeFileSync(join(work, 'complete.json'), JSON.stringify({ layouts: layouts.length, jvmCases: 6, neededDefaultExpansionsPerLayout: 3,
  explicitJvmWithoutHelper: 3, boundaries: boundaries.length, productionUnchanged: true }));
console.log('PASS focused defaults; unused default dependencies remain conservatively required (deferred policy)');
