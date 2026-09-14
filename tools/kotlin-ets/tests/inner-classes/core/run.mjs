import assert from 'node:assert/strict';
import { copyFileSync, mkdirSync, writeFileSync } from 'node:fs';
import { basename, dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { compiler, core, harness, identities, root, sources, hash } from '../../binary-bodies/r2b/support.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const { work, run } = harness(join(here, '.work'));
const fixtures = ['Fixture.kt', 'Generic.kt', 'Derived.kt', 'Secondary.kt', 'Chain.kt'];
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
for (const [name, message] of [['Generic.kt', 'generic'], ['Derived.kt', 'Any-only'],
  ['Secondary.kt', 'primary constructor'], ['Chain.kt', 'top-level outer']]) {
  console.log(run(name, 'java', ['-cp', `${cp}:${jar}`, 'dev.ets.ProbeKt', cp, join(snapshot, name), work, message]).trim());
}
assert.ok(inputs.every(input => hash(input.path) === input.sha256), 'Core changed during probe');
writeFileSync(join(work, 'result.json'), JSON.stringify({ passed: true, inputs, languageParity: 'not tested by core probe' }, null, 2));
