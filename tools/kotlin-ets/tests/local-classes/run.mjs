import assert from 'node:assert/strict';
import { copyFileSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { basename, dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { compiler, core, harness, identities, root, sources, hash } from '../binary-bodies/r2b/support.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const { work, run } = harness(join(here, '.work'));
const fixtures = ['Fixture.kt', 'Captured.kt', 'CapturedType.kt', 'CapturedBase.kt', 'ObservedBase.kt', 'Inner.kt'];
const inputs = identities([...core, ...sources(join(root, 'src/target')), join(here, 'Probe.kt'), ...fixtures.map(name => join(here, name))]);
const snapshot = join(work, 'snapshot');
mkdirSync(snapshot);
const frozen = inputs.map(input => {
  const path = join(snapshot, basename(input.path));
  copyFileSync(input.path, path);
  assert.equal(hash(path), input.sha256);
  return path;
});
writeFileSync(join(work, 'inputs.json'), JSON.stringify(inputs, null, 2));
const cp = run('classpath', 'bash', [compiler, '--classpath']).trim();
const jar = join(work, 'probe.jar');
run('original-kotlin', 'bash', [compiler, ...fixtures.map(name => join(snapshot, name)), '-d', join(work, 'original.jar')]);
run('compile', 'bash', [compiler, ...frozen.filter(path => !fixtures.includes(basename(path))), '-d', jar]);
console.log(run('probe', 'java', ['-cp', `${cp}:${jar}`, 'dev.ets.ProbeKt', cp, join(snapshot, 'Fixture.kt'), work]).trim());
console.log(run('capture-values', 'java', ['-cp', `${cp}:${jar}`, 'dev.ets.ProbeKt', cp, join(snapshot, 'Captured.kt'), work, 'capture-values']).trim());
console.log(run('capture-heritage', 'java', ['-cp', `${cp}:${jar}`, 'dev.ets.ProbeKt', cp, join(snapshot, 'CapturedBase.kt'), work, 'capture-heritage']).trim());
for (const [name, message] of [['CapturedType.kt', 'captured type parameters'],
  ['ObservedBase.kt', 'Using this during inherited initialization'], ['Inner.kt', 'Inner class generic']]) {
  console.log(run(name, 'java', ['-cp', `${cp}:${jar}`, 'dev.ets.ProbeKt', cp, join(snapshot, name), work, message]).trim());
}
assert.ok(inputs.every(input => hash(input.path) === input.sha256), 'Core contract changed during probe');
writeFileSync(join(work, 'result.json'), JSON.stringify({ passed: true, inputs,
  ir: readFileSync(join(work, 'actual.ir'), 'utf8'), languageParity: 'not tested by this core probe' }, null, 2));
