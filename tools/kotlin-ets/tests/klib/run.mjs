import assert from 'node:assert/strict';
import { cpSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';
import { compiler, harness, identities, root, sources, hash } from '../binary-bodies/r2b/support.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const { work, run } = harness(join(here, '.work'));
const cp = run('classpath', 'bash', [compiler, '--classpath']).trim();
const stdlib = process.env.KOTLIN_JS_STDLIB ?? resolve(root, '../../artifacts/kotlin-js-official-prototype-20260913/cache/kotlin-stdlib-js-2.1.20.klib');
assert.ok(existsSync(stdlib), 'Provide the pinned Kotlin 2.1.20 JS stdlib KLIB via KOTLIN_JS_STDLIB');
const fixtures = ['Helper.kt', 'Library.kt', 'Application.kt', 'Oracle.kt'];
const implementation = identities([...sources(join(root, 'src')), ...fixtures.map(name => join(here, name)),
  join(here, 'Load.kt'), fileURLToPath(import.meta.url), stdlib]);
const input = join(work, 'producer');
mkdirSync(input);
for (const name of fixtures) cpSync(join(here, name), join(input, name));
const jvm = join(work, 'oracle.jar');
run('jvm-build', 'bash', [compiler, ...sources(input), '-d', jvm]);
const expected = run('jvm-run', 'java', ['-cp', `${cp}:${jvm}`, 'klibconsumer.OracleKt']).trim().split('\n');
assert.deepEqual(expected, ['Next:24', 'Next:15', 'Explore:30', 'Explore:-2147483630']);
const libs = [];
for (const [name, source] of [['helper', 'Helper.kt'], ['library', 'Library.kt'], ['application', 'Application.kt']]) {
  run(`build-${name}`, 'java', ['-cp', cp, 'org.jetbrains.kotlin.cli.js.K2JSCompiler', '-Xir-produce-klib-file',
    '-ir-output-dir', work, '-ir-output-name', name, '-libraries', [stdlib, ...libs].join(':'), join(input, source)]);
  libs.push(join(work, `${name}.klib`));
}
const binaries = identities(libs);
const probe = join(work, 'probe.jar');
run('probe-build', 'bash', [compiler, ...sources(join(root, 'src')), join(here, 'Load.kt'), '-d', probe]);
const positive = join(work, 'positive');
const missingAdapter = join(work, 'missing-adapter');
mkdirSync(positive);
mkdirSync(missingAdapter);
for (const [mode, output] of [['positive', positive], ['missing-adapter', missingAdapter]]) {
  console.log(run(mode, 'java', ['-cp', `${cp}:${probe}`, 'dev.ets.klibtest.LoadKt', mode, output,
    libs[2], libs[1], libs[0], stdlib]).trim());
}
const rejection = JSON.parse(readFileSync(join(missingAdapter, 'rejection.json')));
assert.equal(rejection.code, 'UNSUPPORTED_KLIB_DEPENDENCY');
assert.ok(rejection.source.file.endsWith('Application.kt'));
assert.ok(rejection.source.start >= 0 && rejection.source.end > rejection.source.start);
assert.equal(rejection.source.line, 6);
assert.equal(rejection.source.column, 59);
assert.match(rejection.signature, /^kliblibrary\/adjusted\|/);
assert.equal(rejection.library, libs[1]);
assert.match(rejection.message, /kliblibrary\/adjusted\|/);
assert.match(rejection.message, /klibhelper\/bias\|/);
assert.match(rejection.message, new RegExp(libs[0].replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
assert.match(rejection.detail, /Fallback decision: no declared typed adapter accepted the call/);
const decisions = readFileSync(join(positive, 'decisions.tsv'), 'utf8').trim().split('\n');
for (const [signature, library] of [
  ['kliblibrary/adjusted|', libs[1]], ['kliblibrary/buttonLabel|', libs[1]],
  ['klibhelper/echo|', libs[0]], ['klibhelper/offset|', libs[0]],
]) assert.ok(decisions.some(line => line.startsWith(`REUSABLE_BODY\t${signature}`) && line.includes(`\t${library}\t`)), signature);
const biasReplacements = decisions.filter(line => line.startsWith('TARGET_REPLACEMENT\tklibhelper/bias|'));
assert.equal(biasReplacements.length, 1);
assert.ok(biasReplacements[0].includes(`\t${libs[0]}\t`));
assert.ok(biasReplacements[0].includes('Helper.kt'));
for (const signature of ['kliblibrary/adjusted|', 'kliblibrary/buttonLabel|', 'klibhelper/echo|', 'klibhelper/offset|']) {
  assert.equal(decisions.filter(line => line.startsWith(`TARGET_REPLACEMENT\t${signature}`)).length, 0);
}
const signatures = {
  Application: { scenario: ['seed'] },
  Library: { adjusted: ['seed'], buttonLabel: ['page'] },
  Helper: { echo: ['value'], offset: ['value'] },
};
const modules = Object.keys(signatures);
for (const name of modules) {
  const code = readFileSync(join(positive, `${name}.ets`), 'utf8');
  writeFileSync(join(positive, `${name}.ts`), code);
  const parsed = ts.createSourceFile(`${name}.ets`, code, ts.ScriptTarget.Latest, true);
  assert.deepEqual(parsed.parseDiagnostics, []);
  const functions = parsed.statements.filter(ts.isFunctionDeclaration);
  assert.deepEqual(Object.fromEntries(functions.map(fn => [fn.name.text,
    fn.parameters.map(parameter => parameter.name.text)])), signatures[name]);
}
const checked = ts.createProgram(modules.map(name => join(positive, `${name}.ts`)), {
  target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, strict: true, noEmit: true, types: [],
});
assert.deepEqual(ts.getPreEmitDiagnostics(checked).map(d => ts.flattenDiagnosticMessageText(d.messageText, '\n')), []);
const cache = new Map();
function execute(name) {
  assert.ok(modules.includes(name), `Unexpected import: ${name}`);
  if (cache.has(name)) return cache.get(name);
  const code = readFileSync(join(positive, `${name}.ets`), 'utf8');
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
const target = execute('Application');
const actual = [1, -2, 3, 2147483647].map(seed => target.scenario(seed));
assert.deepEqual(actual, expected);
assert.deepEqual([...cache.keys()].sort(), modules.toSorted());
const missing = join(work, 'missing-helper');
mkdirSync(missing);
run('missing-helper', 'java', ['-cp', `${cp}:${probe}`, 'dev.ets.klibtest.LoadKt', 'missing-helper', missing,
  libs[2], libs[1], libs[0], stdlib], 1);
const physicalRejection = JSON.parse(readFileSync(join(work, 'missing-helper.json')));
assert.match(physicalRejection.stderr, /KLIB resolver: Could not find "helper"/);
assert.match(physicalRejection.stderr, /module "library" has a reference to symbol klibhelper\/(echo|bias|offset)/i);
for (const name of modules) assert.equal(existsSync(join(missing, `${name}.ets`)), false);
rmSync(input, { recursive: true });
assert.equal(existsSync(input), false);
assert.ok(implementation.every(item => hash(item.path) === item.sha256));
assert.ok(binaries.every(item => hash(item.path) === item.sha256));
writeFileSync(join(work, 'result.json'), JSON.stringify({ passed: true, expected, actual, implementation, binaries,
  producerSourcesAbsentAfterDiagnostics: true, officialLoader: 'loadIr / JsIrLinker',
  translated: ['application'], dependencyOnly: ['library', 'helper'],
  reused: ['adjusted', 'buttonLabel', 'echo', 'offset'], fallback: 'bias by canonical IrFunctionSymbol',
  rejection, strictHostTypecheck: true, missingTransitiveDependencyRejected: true,
  outputs: identities(modules.map(name => join(positive, `${name}.ets`))), sdk: 'run separately', device: 'not run',
  limitation: 'Pinned KLIB proof; not public CLI input support or general JS runtime compatibility',
}, null, 2));
console.log(`PASS ${actual.length} JVM/ETS-host results, transitive bodies, exact fallback, structured rejection`);
console.log(`Evidence: ${work}`);
