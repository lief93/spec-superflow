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
const input = join(work, 'producer');
mkdirSync(input);
for (const name of ['Library', 'Consumer', 'External', 'Rejected', 'Oracle']) cpSync(join(here, `${name}.kt`), join(input, `${name}.kt`));
const oracle = join(work, 'oracle.jar');
run('jvm-build', 'bash', [compiler, ...['Library', 'Consumer', 'Oracle'].map(name => join(input, `${name}.kt`)), '-d', oracle]);
const expected = run('jvm-run', 'java', ['-cp', `${cp}:${oracle}`, 'consumer.OracleKt']).trim().split('\n').map(Number);
assert.deepEqual(expected, [2, 0, 0, -1]);
function klib(name, files, dependencies = []) {
  run(`klib-${name}`, 'java', ['-cp', cp, 'org.jetbrains.kotlin.cli.js.K2JSCompiler', '-Xir-produce-klib-file',
    '-ir-output-dir', work, '-ir-output-name', name, '-libraries', [stdlib, ...dependencies].join(':'),
    ...files.map(file => join(input, `${file}.kt`))]);
  return join(work, `${name}.klib`);
}
const library = klib('library', ['Library']);
const consumer = klib('consumer', ['Consumer'], [library]);
const external = klib('external', ['External']);
const rejected = klib('rejected', ['Rejected'], [external]);
rmSync(input, { recursive: true });
const binaries = identities([library, consumer, external, rejected]);
const probe = join(work, 'probe.jar');
run('probe-build', 'bash', [compiler, ...sources(join(root, 'src')), join(here, 'Load.kt'), '-d', probe]);
for (const [mode, main, dependency] of [['positive', consumer, library], ['external', rejected, external], ['unselected', consumer, library]]) {
  const output = join(work, mode);
  mkdirSync(output);
  console.log(run(mode, 'java', ['-cp', `${cp}:${probe}`, 'dev.ets.capabilitytest.LoadKt', mode, output, main, dependency, stdlib]).trim());
}
const output = join(work, 'positive');
const modules = ['Consumer', 'Library'];
for (const name of modules) writeFileSync(join(output, `${name}.ts`), readFileSync(join(output, `${name}.ets`)));
const checked = ts.createProgram(modules.map(name => join(output, `${name}.ts`)), {
  target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, strict: true, noEmit: true, types: [],
});
assert.deepEqual(ts.getPreEmitDiagnostics(checked).map(d => ts.flattenDiagnosticMessageText(d.messageText, '\n')), []);
const cache = new Map();
function execute(name) {
  assert.ok(modules.includes(name));
  if (cache.has(name)) return cache.get(name);
  const code = readFileSync(join(output, `${name}.ets`), 'utf8');
  const result = ts.transpileModule(code, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS }, reportDiagnostics: true });
  assert.deepEqual(result.diagnostics, []);
  const context = { exports: {}, require: path => { assert.ok(path.startsWith('./')); return execute(path.slice(2)); } };
  cache.set(name, context.exports);
  vm.runInNewContext(result.outputText, context, { timeout: 1000 });
  return context.exports;
}
const target = execute('Consumer');
const actual = [0, 1, -5, 2147483647].map(value => target.scenario(value));
assert.deepEqual(actual, expected);
assert.deepEqual([...cache.keys()].sort(), modules.sort());
const consumerCode = readFileSync(join(output, 'Consumer.ets'), 'utf8');
const ast = ts.createSourceFile('Consumer.ets', consumerCode, ts.ScriptTarget.Latest, true);
assert.deepEqual(ast.statements.filter(node => node.name?.text.startsWith('__ets')).map(node => node.name.text).sort(),
  ['__etsIntRem', '__etsThrowable']);
assert.doesNotMatch(consumerCode, /__etsList|__etsSet|__etsMap|kotlin\.js/);
assert.ok(implementation.every(item => hash(item.path) === item.sha256));
assert.ok(binaries.every(item => hash(item.path) === item.sha256));
writeFileSync(join(work, 'result.json'), JSON.stringify({ passed: true, implementation, binaries,
  expected, actual, producerSourcesAbsent: true, officialInlineBody: 'kotlin.let from pinned stdlib KLIB',
  runtimeSymbols: readFileSync(join(output, 'runtime-symbols.txt'), 'utf8').split('\n'),
  rejected: ['external declaration without replacement', 'non-inline dependency-only body'],
  strictHostTypecheck: true, sdk: 'not run', device: 'not run',
  outputs: identities(modules.map(name => join(output, `${name}.ets`))),
}, null, 2));
console.log('PASS S1 KLIB: official body reuse, minimal runtime selection, typed ETS/JVM oracle, source-linked refusals');
