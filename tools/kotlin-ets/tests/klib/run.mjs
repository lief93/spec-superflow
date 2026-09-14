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
assert.deepEqual(expected, ['Next:9', 'Next:0', 'Explore:15', 'Explore:-2147483645']);
const libs = [];
for (const [name, source] of [['helper', 'Helper.kt'], ['library', 'Library.kt'], ['application', 'Application.kt']]) {
  run(`build-${name}`, 'java', ['-cp', cp, 'org.jetbrains.kotlin.cli.js.K2JSCompiler', '-Xir-produce-klib-file',
    '-ir-output-dir', work, '-ir-output-name', name, '-libraries', [stdlib, ...libs].join(':'), join(input, source)]);
  libs.push(join(work, `${name}.klib`));
}
rmSync(input, { recursive: true });
assert.equal(existsSync(input), false);
const binaries = identities(libs);
const probe = join(work, 'probe.jar');
run('probe-build', 'bash', [compiler, ...sources(join(root, 'src')), join(here, 'Load.kt'), '-d', probe]);
console.log(run('load', 'java', ['-cp', `${cp}:${probe}`, 'dev.ets.klibtest.LoadKt', work, libs[2], stdlib, libs[0], libs[1]]).trim());
const signatures = {
  Application: { scenario: ['seed'] },
  Library: { adjusted: ['seed'], buttonLabel: ['page'] },
  Helper: { echo: ['value'], offset: ['value'] },
};
const modules = Object.keys(signatures);
for (const name of modules) {
  const code = readFileSync(join(work, `${name}.ets`), 'utf8');
  writeFileSync(join(work, `${name}.ts`), code);
  const parsed = ts.createSourceFile(`${name}.ets`, code, ts.ScriptTarget.Latest, true);
  assert.deepEqual(parsed.parseDiagnostics, []);
  const functions = parsed.statements.filter(ts.isFunctionDeclaration);
  assert.deepEqual(Object.fromEntries(functions.map(fn => [fn.name.text,
    fn.parameters.map(parameter => parameter.name.text)])), signatures[name]);
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
const target = execute('Application');
const actual = [1, -2, 3, 2147483647].map(seed => target.scenario(seed));
assert.deepEqual(actual, expected);
assert.deepEqual([...cache.keys()].sort(), modules.sort());
const missing = join(work, 'missing-helper');
mkdirSync(missing);
run('missing-helper', 'java', ['-cp', `${cp}:${probe}`, 'dev.ets.klibtest.LoadKt', missing, libs[2], stdlib, libs[1]], 1);
const rejection = JSON.parse(readFileSync(join(work, 'missing-helper.json')));
assert.match(rejection.stderr, /KLIB resolver: Could not find "helper"/);
assert.match(rejection.stderr, /module "library" has a reference to symbol klibhelper\/echo/i);
for (const name of modules) assert.equal(existsSync(join(missing, `${name}.ets`)), false);
assert.ok(implementation.every(item => hash(item.path) === item.sha256));
assert.ok(binaries.every(item => hash(item.path) === item.sha256));
writeFileSync(join(work, 'result.json'), JSON.stringify({ passed: true, expected, actual, implementation, binaries,
  producerSourcesAbsent: true, officialLoader: 'loadIr / JsIrLinker', moduleOrderInvariant: true,
  strictHostTypecheck: true, missingTransitiveDependencyRejected: true,
  outputs: identities(modules.map(name => join(work, `${name}.ets`))), sdk: 'not run', device: 'not run',
  limitation: 'Separate pinned KLIB proof; not public CLI input support or general JS runtime compatibility',
}, null, 2));
console.log(`PASS ${actual.length} JVM/ETS-host results, preserved names, strict imports/types, missing dependency rejection`);
