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
assert.ok(existsSync(stdlib), 'Provide Kotlin 2.1.20 KOTLIN_JS_STDLIB (linker signatures only)');
const fixtures = ['Bodies.kt', 'Consumer.kt', 'Primitives.kt', 'JvmPrimitives.kt', 'Oracle.kt', 'Load.kt'];
const implementation = identities([...sources(join(root, 'src')), ...fixtures.map(name => join(here, name)), fileURLToPath(import.meta.url), stdlib]);
const producer = join(work, 'producer');
mkdirSync(producer);
for (const name of ['Bodies.kt', 'Consumer.kt', 'Primitives.kt', 'JvmPrimitives.kt', 'Oracle.kt']) {
  cpSync(join(here, name), join(producer, name));
}
const jvm = join(work, 'oracle.jar');
run('jvm-build', 'bash', [compiler, ...['Bodies.kt', 'Consumer.kt', 'JvmPrimitives.kt', 'Oracle.kt'].map(name => join(producer, name)), '-d', jvm]);
const expected = run('jvm-run', 'java', ['-cp', `${cp}:${jvm}`, 'portableconsumer.OracleKt']).trim().split('\n');
const libs = [];
for (const [name, file] of [['primitives', 'Primitives.kt'], ['bodies', 'Bodies.kt'], ['consumer', 'Consumer.kt']]) {
  run(`build-${name}`, 'java', ['-cp', cp, 'org.jetbrains.kotlin.cli.js.K2JSCompiler', '-Xir-produce-klib-file',
    '-ir-output-dir', work, '-ir-output-name', name, '-libraries', [stdlib, ...libs].join(':'), join(producer, file)]);
  libs.push(join(work, `${name}.klib`));
}
rmSync(producer, { recursive: true });
assert.equal(existsSync(producer), false);
const binaries = identities(libs);
const probe = join(work, 'probe.jar');
run('probe-build', 'bash', [compiler, ...sources(join(root, 'src')), join(here, 'Load.kt'), '-d', probe]);
console.log(run('lower', 'java', ['-cp', `${cp}:${probe}`, 'dev.ets.portabletest.LoadKt', work, libs[2], libs[1], libs[0], stdlib]).trim());
const modules = ['Bodies', 'Consumer'];
for (const name of modules) {
  const code = readFileSync(join(work, `${name}.ets`), 'utf8');
  assert.doesNotMatch(code, /__etsListMap|__etsListFilter|__etsIntProgression|__etsProgressionIterator|kotlin\.js/);
  const parsed = ts.createSourceFile(`${name}.ets`, code, ts.ScriptTarget.Latest, true);
  assert.deepEqual(parsed.parseDiagnostics, []);
  const helpers = parsed.statements.filter(statement => statement.name?.text.startsWith('__ets'))
    .map(statement => statement.name.text).sort();
  assert.deepEqual(helpers, name === 'Bodies' ? ['__etsListAdd', '__etsThrowable'] : ['__etsIntRem', '__etsThrowable']);
  if (name === 'Bodies') {
    const map = parsed.statements.find(statement => ts.isFunctionDeclaration(statement) && statement.name.text === 'mapBody');
    assert.equal(map.typeParameters.length, 1);
    let loops = 0;
    function visit(node) { if (ts.isWhileStatement(node)) loops++; ts.forEachChild(node, visit); }
    visit(map);
    assert.equal(loops, 1, 'The loaded generic map body must contain its own iteration loop');
  }
  writeFileSync(join(work, `${name}.ts`), code);
}
const checked = ts.createProgram(modules.map(name => join(work, `${name}.ts`)), {
  target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, strict: true, noEmit: true, types: [],
});
assert.deepEqual(ts.getPreEmitDiagnostics(checked).map(d => ts.flattenDiagnosticMessageText(d.messageText, '\n')), []);
const cache = new Map();
function execute(name) {
  assert.ok(modules.includes(name), `Unexpected import: ${name}`);
  if (cache.has(name)) return cache.get(name);
  const code = readFileSync(join(work, `${name}.ets`), 'utf8');
  const compiled = ts.transpileModule(code, { compilerOptions: {
    target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS }, reportDiagnostics: true });
  assert.deepEqual(compiled.diagnostics, []);
  const context = { exports: {}, require: path => {
    assert.ok(path.startsWith('./'));
    return execute(path.slice(2));
  } };
  cache.set(name, context.exports);
  vm.runInNewContext(compiled.outputText, context, { timeout: 1000 });
  return context.exports;
}
const target = execute('Consumer');
// Bound calls too: an Int.MAX_VALUE termination regression must fail, not hang.
const invoke = (name, ...args) => vm.runInNewContext('target[name](...args)', { target, name, args }, { timeout: 1000 });
const cases = [[1, 4], [4, 1], [-2, 2], [0, 0], [2147483646, 2147483647],
  [-2147483648, -2147483647], [-2147483648, -2147483648], [2147483647, 2147483647], [2147483647, -2147483648]];
const render = values => Array.from(values, value => value === null ? 'null' : String(value)).join(',');
const actual = cases.map(([first, last]) => {
  assert.throws(() => invoke('exhaustedAfter', first, last), error => error.name === 'NoSuchElementException' && error.sourceMessage === null);
  return [render(invoke('mapped', first, last)), render(invoke('strings', first, last)),
    render(invoke('nullable', first, last)), invoke('order', first, last)].join('|');
});
actual.push(invoke('independent'));
let trace = '';
const sentinel = new Error('callback sentinel');
assert.throws(() => invoke('callback', 1, 4, value => {
  trace += `${value},`;
  if (value === 3) throw sentinel;
  return value;
}), error => error === sentinel);
actual.push(trace);
assert.deepEqual(actual, expected);
assert.equal(actual.length, 11);
assert.ok(implementation.every(item => hash(item.path) === item.sha256));
assert.ok(binaries.every(item => hash(item.path) === item.sha256));
writeFileSync(join(work, 'result.json'), JSON.stringify({ passed: true, cases, expected, actual,
  implementation, binaries, outputs: identities(modules.map(name => join(work, `${name}.ets`))),
  stdlibBodyIndependence: true, removedStdlibBodies: Number(readFileSync(join(work, 'removed-stdlib-bodies.txt'), 'utf8')),
  producerSourcesAbsent: true, translatedModules: modules, actualPrimitives: ['newList', 'append', 'exhausted'],
  runtimeSymbols: readFileSync(join(work, 'runtime-symbols.txt'), 'utf8').split('\n'),
  strictHostTypecheck: true, moduleOrderAlphaEquivalent: true, jvmNativeStdlibOracle: true,
  exhaustionCases: cases.length, callbackExceptionIdentity: true, sdk: 'not run', device: 'not run',
  limitation: 'Equivalent pure bodies for ascending unit-step IntRange plus generic map; no automatic stdlib substitution or public CLI',
}, null, 2));
console.log(`PASS ${cases.length * 4} JVM/ETS value cases, ${cases.length} exhaustion cases, independent cursors, callback exception identity`);
