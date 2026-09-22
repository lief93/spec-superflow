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
const expected = run('jvm-run', 'java', ['-cp', `${cp}:${oracle}`, 'collectionmapcommon.OracleKt']).trim().split('\n');
assert.deepEqual(expected, ['2,3,4,5|1,2', '|',
  '-2147483647,-2,-1,1,-2147483648|-1073741824,-1,0']);
run('klib-consumer', 'java', ['-cp', cp, 'org.jetbrains.kotlin.cli.js.K2JSCompiler', '-Xir-produce-klib-file',
  '-ir-output-dir', work, '-ir-output-name', 'consumer', '-libraries', stdlib, join(producer, 'Consumer.kt')]);
rmSync(producer, { recursive: true });
const consumer = join(work, 'consumer.klib');
const probe = join(work, 'probe.jar');
run('probe-build', 'bash', [compiler, ...sources(join(root, 'src')), join(here, 'Load.kt'), '-d', probe]);
console.log(run('lower', 'java', ['-cp', `${cp}:${probe}`, 'dev.ets.collectionmapcommontest.LoadKt', work, consumer, stdlib]).trim());
const rejected = join(work, 'rejected');
mkdirSync(rejected);
console.log(run('reject', 'java', ['-cp', `${cp}:${probe}`, 'dev.ets.collectionmapcommontest.LoadKt', rejected,
  consumer, stdlib, 'reject-capacity']).trim());
const rejection = readFileSync(join(rejected, 'rejection.tsv'), 'utf8').trim();
assert.match(rejection, /^UNSUPPORTED_KLIB_DEPENDENCY\t/);
assert.match(rejection, /ArrayList\.kt/);
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
const actual = cases.map(values =>
  `${Array.from(context.exports.mapShift(values)).join(',')}|${Array.from(context.exports.mapEvenHalves(values)).join(',')}`);
assert.deepEqual(actual, expected);
assert.doesNotMatch(code, /__etsListMap|kotlin\.js/);
assert.ok(implementation.every(item => hash(item.path) === item.sha256));
const binary = identities([consumer]);
assert.ok(binary.every(item => hash(item.path) === item.sha256));
writeFileSync(join(work, 'result.json'), JSON.stringify({ passed: true, expected, actual, implementation, binary,
  producerSourcesAbsent: true, strictHostTypecheck: true,
  officialBodies: readFileSync(join(work, 'official-bodies.txt'), 'utf8').split('\n'),
  runtimeSymbols: readFileSync(join(work, 'runtime-symbols.txt'), 'utf8').split('\n'), rejection,
  silentFallback: false, sdk: 'not run', device: 'not run' }, null, 2));
console.log('PASS map/mapNotNull JVM/typed-ETS parity without direct map helper');
