// Run only with an exclusive CLI slot after all production writers freeze.
import assert from 'node:assert/strict';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';
import { boundaries, expected, layouts, seeds } from './cases.mjs';
import { harness, identities, root, sources, hash } from '../r2b/support.mjs';

const here = dirname(fileURLToPath(import.meta.url));
assert.ok(process.argv[2], 'Pass a completed focused r2d directory');
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
  const jvm = run(`${name}-jvm`, 'java', ['-cp', `${classpath}:${join(producer, `${name}-oracle.jar`)}`, 'overloadconsumer.OracleKt']).trim().split('\n');
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
  results.push({ name, expected: jvm, actual, output, sha256: hash(output) });
  writeFileSync(join(work, 'runtime.json'), JSON.stringify(results, null, 2));
  assert.deepEqual(actual, jvm);
}
for (const [name, jars, , message] of boundaries) {
  const output = join(work, `${name}.ets`);
  const file = join(here, 'SelectedDouble.kt');
  const diagnostic = JSON.parse(run(`${name}-cli`, 'bash', [join(root, 'kotlin-ets'), '--mode', 'language',
    '--classpath', [cp, ...jars.map(jar => join(producer, jar))].join(':'), '--out', output, file], 2));
  assert.equal(diagnostic.code, 'UNSUPPORTED');
  assert.match(diagnostic.message, message);
  assert.equal(diagnostic.source.file, file);
  assert.ok(diagnostic.source.start >= 0 && diagnostic.source.end > diagnostic.source.start);
  assert.equal(existsSync(output), false);
}
assert.ok(implementation.every(item => hash(item.path) === item.sha256), 'Production changed during replay');
writeFileSync(join(work, 'complete.json'), JSON.stringify({ layouts: 3, jvmTargetPairs: 9,
  selectedOverloadFailures: 3, implementationUnchanged: true }));
console.log('PASS public binary overloads: nine JVM/host pairs and three selected-overload failures');
