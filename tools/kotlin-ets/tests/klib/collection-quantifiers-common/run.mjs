import assert from 'node:assert/strict';
import { cpSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';
import { compiler, harness, identities, root, sources, hash } from '../../binary-bodies/r2b/support.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const { work, run } = harness(join(here, '.work'));
const cp = run('classpath', 'bash', [compiler, '--classpath']).trim();
const stdlib = process.env.KOTLIN_JS_STDLIB ?? resolve(root, '../../artifacts/kotlin-js-official-prototype-20260913/cache/kotlin-stdlib-js-2.1.20.klib');
assert.ok(existsSync(stdlib), 'Provide pinned Kotlin 2.1.20 KOTLIN_JS_STDLIB');
const implementation = identities([...sources(join(root, 'src')), ...sources(here), fileURLToPath(import.meta.url), stdlib]);
const producer = join(work, 'producer');
mkdirSync(producer);
for (const name of ['Consumer.kt', 'Oracle.kt']) cpSync(join(here, name), join(producer, name));
const oracle = join(work, 'oracle.jar');
run('jvm-build', 'bash', [compiler, ...sources(producer), '-d', oracle]);
const expected = run('jvm-run', 'java', ['-cp', `${cp}:${oracle}`, 'collectionquantifierscommon.OracleKt']).trim().split('\n');
assert.deepEqual(expected, ['false', 'true', 'true', 'false', '0', '21', '1', '20', '21', '1', '20', '21']);
run('klib-consumer', 'java', ['-cp', cp, 'org.jetbrains.kotlin.cli.js.K2JSCompiler', '-Xir-produce-klib-file',
  '-ir-output-dir', work, '-ir-output-name', 'consumer', '-libraries', stdlib, join(producer, 'Consumer.kt')]);
rmSync(producer, { recursive: true });
const consumer = join(work, 'consumer.klib');
const probe = join(work, 'probe.jar');
run('probe-build', 'bash', [compiler, ...sources(join(root, 'src')), join(here, 'Load.kt'), '-d', probe]);
for (const mode of ['positive', 'reject-body', 'reject-has-next']) {
  const output = join(work, mode);
  mkdirSync(output);
  console.log(run(mode, 'java', ['-cp', `${cp}:${probe}`, 'dev.ets.collectionquantifierscommontest.LoadKt',
    output, consumer, stdlib, mode]).trim());
}
const output = join(work, 'positive');
const modules = ['Consumer', '_Collections'];
for (const name of modules) writeFileSync(join(output, `${name}.ts`), readFileSync(join(output, `${name}.ets`)));
const checked = ts.createProgram(modules.map(name => join(output, `${name}.ts`)), {
  target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, strict: true, noEmit: true, types: [],
});
assert.deepEqual(ts.getPreEmitDiagnostics(checked).map(d => ts.flattenDiagnosticMessageText(d.messageText, '\n')), []);
const cache = new Map();
function execute(name) {
  if (cache.has(name)) return cache.get(name);
  assert.ok(modules.includes(name));
  const code = readFileSync(join(output, `${name}.ets`), 'utf8');
  const compiled = ts.transpileModule(code, { compilerOptions: {
    target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS }, reportDiagnostics: true });
  assert.deepEqual(compiled.diagnostics, []);
  const context = { exports: {}, require: path => { assert.ok(path.startsWith('./')); return execute(path.slice(2)); } };
  cache.set(name, context.exports);
  vm.runInNewContext(compiled.outputText, context, { timeout: 1000 });
  return context.exports;
}
const target = execute('Consumer');
const actual = [
  target.anyValue([]), target.anyValue([1]), target.noneValue([]), target.noneValue([1]),
  target.anyMatching([], 2), target.anyMatching([1, 2, 3], 2),
  target.allDifferent([], 2), target.allDifferent([1, 2, 3], 2), target.allDifferent([1, 3], 2),
  target.noneMatching([], 2), target.noneMatching([1, 2, 3], 2), target.noneMatching([1, 3], 2),
].map(String);
assert.deepEqual(actual, expected);
for (const mode of ['reject-body', 'reject-has-next']) {
  const rejection = readFileSync(join(work, mode, 'rejection.tsv'), 'utf8');
  assert.match(rejection, /^UNSUPPORTED_KLIB_DEPENDENCY\t/);
  assert.match(rejection, /\.kt/);
  assert.ok(!existsSync(join(work, mode, 'Consumer.ets')));
}
const code = modules.map(name => readFileSync(join(output, `${name}.ets`), 'utf8')).join('\n');
assert.doesNotMatch(code, /__etsListAny/);
assert.ok(implementation.every(item => hash(item.path) === item.sha256));
const binary = identities([consumer]);
assert.ok(binary.every(item => hash(item.path) === item.sha256));
writeFileSync(join(work, 'result.json'), JSON.stringify({ passed: true, expected, actual, implementation, binary,
  producerSourcesAbsent: true, strictHostTypecheck: true, emptyIdentities: true, shortCircuitOrder: true,
  ordinaryBodies: ['kotlin.collections.any()', 'kotlin.collections.none()'],
  inlineBodies: ['kotlin.collections.any(predicate)', 'kotlin.collections.all(predicate)', 'kotlin.collections.none(predicate)'],
  bodyRejection: true, primitiveRejection: true,
  runtimeSymbols: readFileSync(join(output, 'runtime-symbols.txt'), 'utf8').split('\n'),
  sdk: 'not run', device: 'not run' }, null, 2));
console.log('PASS quantifier JVM/typed-ETS identity, short-circuit, and callback semantics');
