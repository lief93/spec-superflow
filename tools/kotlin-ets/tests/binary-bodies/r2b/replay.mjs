// Requires all production writers frozen and an exclusive full-CLI slot.
import assert from 'node:assert/strict';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';
import { boundaries, expected, layouts, seeds } from './cases.mjs';
import { harness, here, identities, root, sources, hash } from './support.mjs';

assert.ok(process.argv[2], 'Pass a completed focused r2b work directory');
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
  const jvm = run(`${name}-jvm`, 'java', ['-cp', `${classpath}:${join(producer, `${name}-oracle.jar`)}`, 'extensionconsumer.OracleKt']).trim().split('\n');
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
  let exactIdentityChecks = 0;
  for (const seed of seeds) {
    const direct = new context.exports.Box(seed);
    const entry = new context.exports.Box(seed);
    const returnedDirect = context.exports.directIdentity(direct);
    const returnedEntry = context.exports.entryIdentity(entry);
    assert.strictEqual(returnedDirect, direct);
    assert.strictEqual(returnedEntry, entry);
    assert.notStrictEqual(returnedDirect, returnedEntry);
    assert.equal(direct.value, (seed + 1) | 0);
    assert.equal(entry.value, (seed + 1) | 0);
    returnedDirect.value = (returnedDirect.value + 7) | 0;
    returnedEntry.value = (returnedEntry.value + 7) | 0;
    assert.equal(direct.value, (seed + 8) | 0);
    assert.equal(entry.value, (seed + 8) | 0);
    exactIdentityChecks += 2;
  }
  results.push({ name, expected: jvm, actual, exactIdentityChecks, output, sha256: hash(output) });
  writeFileSync(join(work, 'runtime.json'), JSON.stringify(results, null, 2));
  assert.deepEqual(actual, jvm);
}
const negativeCases = [...boundaries, ['reference-equality', ['combined.jar'], 'ReferenceEqualityApplication.kt', null,
  /Unsupported external call: kotlin.internal.ir.EQEQEQ/]];
for (const [name, jars, source, , message] of negativeCases) {
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
writeFileSync(join(work, 'complete.json'), JSON.stringify({ layouts: layouts.length, jvmTargetPairs: 6,
  exactIdentityChecks: 12, closedFailures: negativeCases.length, implementationUnchanged: true }));
console.log('PASS public CLI extension replay: six JVM/host pairs, twelve exact-object checks and nine closed failures');
