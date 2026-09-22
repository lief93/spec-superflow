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
const expected = run('jvm-run', 'java', ['-cp', `${cp}:${oracle}`, 'collectionmapindexedcommon.OracleKt']).trim().split('\n');
assert.deepEqual(expected, ['1,3,5,7|-1,-1', '|',
  '-2147483648,-2,0,3,-2147483645|-2147483648,4,3']);
run('klib-consumer', 'java', ['-cp', cp, 'org.jetbrains.kotlin.cli.js.K2JSCompiler', '-Xir-produce-klib-file',
  '-ir-output-dir', work, '-ir-output-name', 'consumer', '-libraries', stdlib, join(producer, 'Consumer.kt')]);
rmSync(producer, { recursive: true });
const consumer = join(work, 'consumer.klib');
const probe = join(work, 'probe.jar');
run('probe-build', 'bash', [compiler, ...sources(join(root, 'src')), join(here, 'Load.kt'), '-d', probe]);
console.log(run('lower', 'java', ['-cp', `${cp}:${probe}`, 'dev.ets.collectionmapindexedcommontest.LoadKt', work,
  consumer, stdlib]).trim());
const rejected = join(work, 'rejected');
mkdirSync(rejected);
console.log(run('reject', 'java', ['-cp', `${cp}:${probe}`, 'dev.ets.collectionmapindexedcommontest.LoadKt', rejected,
  consumer, stdlib, 'reject-index-check']).trim());
const rejection = readFileSync(join(rejected, 'rejection.tsv'), 'utf8').trim();
assert.match(rejection, /^UNSUPPORTED_KLIB_DEPENDENCY\t/);
assert.match(rejection, /collectionJs\.kt/);
assert.match(rejection, /Consumer\.kt/);
assert.ok(!existsSync(join(rejected, 'Consumer.ets')));
const code = readFileSync(join(work, 'Consumer.ets'), 'utf8');
const typed = join(work, 'Consumer.ts');
writeFileSync(typed, code);
const checked = ts.createProgram([typed], { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS,
  strict: true, noEmit: true, types: [] });
assert.deepEqual(ts.getPreEmitDiagnostics(checked).map(d => ts.flattenDiagnosticMessageText(d.messageText, '\n')), []);
const compiled = ts.transpileModule(code, { compilerOptions: { target: ts.ScriptTarget.ES2022,
  module: ts.ModuleKind.CommonJS }, reportDiagnostics: true });
assert.deepEqual(compiled.diagnostics, []);
const context = { exports: {} };
vm.runInNewContext(compiled.outputText, context, { timeout: 1000 });
const cases = [[1, 2, 3, 4], [], [-2147483648, -3, -2, 0, 2147483647]];
const actual = cases.map(values => `${Array.from(context.exports.mapIndexedSum(values)).join(',')}|` +
  `${Array.from(context.exports.mapIndexedEvenOffsets(values)).join(',')}`);
assert.deepEqual(actual, expected);
assert.doesNotMatch(code, /__etsListMap|kotlin\.js/);
assert.match(code, /\+ 1 \| 0/);
assert.match(code, /< 0/);
assert.match(code, /Index overflow has happened\./);
const overflowCode = code.replace('let index: number = 0;', 'let index: number = 2147483647;');
assert.notEqual(overflowCode, code, 'Expected indexed map state for overflow fault injection');
const overflowCompiled = ts.transpileModule(overflowCode, { compilerOptions: { target: ts.ScriptTarget.ES2022,
  module: ts.ModuleKind.CommonJS }, reportDiagnostics: true });
assert.deepEqual(overflowCompiled.diagnostics, []);
const overflowContext = { exports: {} };
vm.runInNewContext(overflowCompiled.outputText, overflowContext, { timeout: 1000 });
assert.throws(() => overflowContext.exports.mapIndexedSum([1, 2]), error => {
  assert.equal(error.name, 'ArithmeticException');
  assert.equal(error.sourceMessage, 'Index overflow has happened.');
  return true;
});
assert.ok(implementation.every(item => hash(item.path) === item.sha256));
const binary = identities([consumer]);
assert.ok(binary.every(item => hash(item.path) === item.sha256));
writeFileSync(join(work, 'result.json'), JSON.stringify({ passed: true, expected, actual, implementation, binary,
  producerSourcesAbsent: true, strictHostTypecheck: true, intIndexWrapAndOverflowCheck: true,
  faultInjectedOverflowBranch: true,
  officialBodies: readFileSync(join(work, 'official-bodies.txt'), 'utf8').split('\n'),
  runtimeSymbols: readFileSync(join(work, 'runtime-symbols.txt'), 'utf8').split('\n'), rejection,
  silentFallback: false, sdk: 'not run', device: 'not run' }, null, 2));
console.log('PASS indexed-map JVM/typed-ETS parity, Int index semantics, and null filtering');
