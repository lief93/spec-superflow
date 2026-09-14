// Requires frozen production and an exclusive public-CLI slot.
import assert from 'node:assert/strict';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';
import { boundaries, expected, layouts, seeds } from './cases.mjs';
import { harness, identities, root, sources, hash } from '../r2b/support.mjs';

const here = dirname(fileURLToPath(import.meta.url));
assert.ok(process.argv[2], 'Pass a completed focused r2c work directory');
const producer = resolve(process.argv[2]);
const inputs = JSON.parse(readFileSync(join(producer, 'producers.json'), 'utf8'));
assert.ok(inputs.every(item => hash(item.path) === item.sha256), 'Producer/test inputs changed after focused evidence');
const { work, run } = harness(producer, 'public-');
const cp = JSON.parse(readFileSync(join(producer, 'classpath.json'), 'utf8')).stdout.trim();
const implementation = identities([join(root, 'kotlin-ets'), ...sources(join(root, 'src'))].sort());
writeFileSync(join(work, 'identity.json'), JSON.stringify({ implementation, inputs }, null, 2));
const results = [];
for (const [name, jars] of layouts) {
  const classpath = [cp, ...jars.map(jar => join(producer, jar))].join(':');
  const jvm = run(`${name}-jvm`, 'java', ['-cp', `${classpath}:${join(producer, `${name}-oracle.jar`)}`, 'defaultconsumer.OracleKt']).trim().split('\n');
  assert.deepEqual(jvm, expected);
  const output = join(work, `${name}.ets`);
  run(`${name}-cli`, 'bash', [join(root, 'kotlin-ets'), '--mode', 'language', '--classpath', classpath, '--out', output, join(here, 'Application.kt')]);
  const compiled = ts.transpileModule(readFileSync(output, 'utf8'), {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS }, reportDiagnostics: true,
  });
  assert.deepEqual(compiled.diagnostics, []);
  const context = { exports: {} };
  vm.runInNewContext(compiled.outputText, context, { timeout: 1000 });
  const actual = seeds.map(seed => context.exports.scenario(seed));
  for (const seed of seeds) {
    const receiver = new context.exports.Box(seed);
    const selected = new context.exports.Box(seed);
    const omitted = context.exports.defaultIdentity(receiver);
    const explicit = context.exports.explicitIdentity(receiver, selected);
    assert.strictEqual(omitted, receiver);
    assert.strictEqual(explicit, selected);
    assert.notStrictEqual(explicit, receiver);
    omitted.value = (omitted.value + 3) | 0;
    explicit.value = (explicit.value + 4) | 0;
    assert.equal(receiver.value, (seed + 3) | 0);
    assert.equal(selected.value, (seed + 4) | 0);
  }
  results.push({ name, expected: jvm, actual, exactIdentityChecks: 6, output, sha256: hash(output) });
  writeFileSync(join(work, 'runtime.json'), JSON.stringify(results, null, 2));
  assert.deepEqual(actual, jvm);
}
assert.deepEqual(run('explicit-jvm-without-helper', 'java', ['-cp', `${cp}:${join(producer, 'entry.jar')}:${join(producer, 'explicit-oracle.jar')}`,
  'defaultconsumer.ExplicitOracleKt']).trim().split('\n'), ['11', '8', '-2147483639']);
for (const [name, jars, source, , message] of boundaries) {
  const output = join(work, `${name}.ets`);
  const file = join(here, source);
  const diagnostic = JSON.parse(run(`${name}-cli`, 'bash', [join(root, 'kotlin-ets'), '--mode', 'language',
    '--classpath', [cp, ...jars.map(jar => join(producer, jar))].join(':'), '--out', output, file], 2));
  assert.equal(diagnostic.code, 'UNSUPPORTED');
  assert.match(diagnostic.message, message);
  assert.equal(diagnostic.source.file, file);
  assert.ok(diagnostic.source.start >= 0 && diagnostic.source.end > diagnostic.source.start);
  assert.equal(existsSync(output), false);
}
assert.ok(implementation.every(item => hash(item.path) === item.sha256), 'Production changed during replay');
writeFileSync(join(work, 'complete.json'), JSON.stringify({ layouts: layouts.length, jvmTargetPairs: 6, exactIdentityChecks: 12,
  closedFailures: boundaries.length, unusedDefaultDependencyPolicy: 'conservative; call-sensitive loading deferred', implementationUnchanged: true }));
console.log('PASS public defaults: six JVM/host pairs, twelve object checks, five closed failures including unused-default policy');
