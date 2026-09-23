import assert from 'node:assert/strict';
import { cpSync, existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';
import { compiler, harness, identities, root, sources, hash } from '../binary-bodies/r2b/support.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const fixtures = join(here, 'fixtures');
const module = join(here, 'module');
const { work, run } = harness(join(here, '.work'));
const cp = run('classpath', 'bash', [compiler, '--classpath']).trim();
const api = join(work, 'dependency.jar');
run('dependency', 'bash', [compiler, join(fixtures, 'Dependency.kt'), '-d', api]);
const tool = join(work, 'tool.jar');
run('tool', 'bash', [compiler, ...sources(join(root, 'src')), ...sources(join(module, 'src')), '-d', tool]);
const spi = join(work, 'spi/META-INF/services');
mkdirSync(spi, { recursive: true });
cpSync(join(module, 'META-INF/services/dev.ets.AdapterModule'), join(spi, 'dev.ets.AdapterModule'));
run('spi', 'jar', ['uf', tool, '-C', join(work, 'spi'), 'META-INF/services/dev.ets.AdapterModule']);
const implementation = identities([...sources(join(root, 'src')), ...sources(here), fileURLToPath(import.meta.url)]);
const classpath = `${cp}:${api}`;
function compile(label, names, status = 0, outDir = false) {
  const output = join(work, outDir ? label : `${label}.ets`);
  const preflight = join(work, `${label}.preflight.json`);
  const args = ['-cp', `${cp}:${tool}`, 'dev.ets.MainKt', '--mode', 'language', '--classpath', classpath,
    outDir ? '--out-dir' : '--out', output, '--preflight-out', preflight,
    ...names.map(name => join(fixtures, `${name}.kt`))];
  const stdout = run(label, 'java', args, status);
  return { output, preflight, stdout, report: JSON.parse(readFileSync(preflight)) };
}
const positive = compile('positive', ['Models', 'Calls'], 0, true);
const generated = ['Models', 'Calls'];
for (const name of generated) assert.ok(existsSync(join(positive.output, `${name}.ets`)));
cpSync(join(here, 'InjectionHost.ets'), join(positive.output, 'InjectionHost.ets'));
const calls = readFileSync(join(positive.output, 'Calls.ets'), 'utf8');
assert.match(calls, /return providedState;/);
assert.match(calls, /return providedBox;/);
assert.match(calls, /return new ConstructedHolder\("constructed"\);/);
assert.match(calls, /return localState\(\);/);
assert.doesNotMatch(calls, /projectdependency|source dependency only/);
for (const name of [...generated, 'InjectionHost']) {
  const code = readFileSync(join(positive.output, `${name}.ets`), 'utf8');
  writeFileSync(join(positive.output, `${name}.ts`), code);
  assert.deepEqual(ts.createSourceFile(`${name}.ets`, code, ts.ScriptTarget.Latest, true).parseDiagnostics, []);
}
const checked = ts.createProgram([...generated, 'InjectionHost'].map(name => join(positive.output, `${name}.ts`)), {
  target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, strict: true, noEmit: true, types: [],
});
assert.deepEqual(ts.getPreEmitDiagnostics(checked).map(d => ts.flattenDiagnosticMessageText(d.messageText, '\n')), []);
const cache = new Map();
function execute(name) {
  if (cache.has(name)) return cache.get(name);
  const code = readFileSync(join(positive.output, `${name}.ets`), 'utf8');
  const compiled = ts.transpileModule(code, { compilerOptions: {
    target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS }, reportDiagnostics: true });
  assert.deepEqual(compiled.diagnostics, []);
  const context = { exports: {}, require: path => execute(path.replace(/^\.\//, '')) };
  cache.set(name, context.exports);
  vm.runInNewContext(compiled.outputText, context, { timeout: 1000 });
  return context.exports;
}
const target = execute('Calls');
assert.deepEqual([target.injectedState().label, target.injectedBox().value.label,
  target.constructedState().label, target.bodyFirst().label], ['injected', 'injected', 'constructed', 'body']);
assert.equal(positive.report.firstUnsupportedNode, null);

const negatives = [
  ['missing', 'Missing', 'PROJECT_ADAPTER_MISSING', 'project_adapter_missing', 37],
  ['wrong', 'Wrong', 'PROJECT_ADAPTER_RETURN_TYPE', 'project_adapter_return_type', 33],
  ['void', 'Void', 'PROJECT_ADAPTER_VOID_RESULT', 'project_adapter_void_result', 31],
  ['arguments', 'Arguments', 'PROJECT_ADAPTER_ARGUMENTS', 'project_adapter_arguments', 39],
  ['scope', 'Scope', 'PROJECT_ADAPTER_SCOPE', 'project_adapter_scope', 34],
  ['overload', 'Overload', 'UNSUPPORTED', 'project_adapter_missing', 38],
];
const failures = [];
for (const [label, fixture, code, kind, column] of negatives) {
  const result = compile(label, ['Models', fixture], 2);
  assert.equal(existsSync(result.output), false);
  const failure = JSON.parse(result.stdout.trim().split('\n').at(-1));
  assert.equal(failure.code, code);
  assert.ok(failure.source.file.endsWith(`${fixture}.kt`));
  assert.equal(failure.source.line, 5);
  assert.equal(failure.source.column, column);
  const call = result.report.calls.find(value => value.source.file.endsWith(`${fixture}.kt`) &&
    value.category === 'project_dependencies');
  assert.equal(call.firstUnsupportedNode.kind, kind);
  assert.equal(call.firstUnsupportedNode.source.line, failure.source.line);
  assert.equal(call.firstUnsupportedNode.source.column, failure.source.column);
  failures.push({ label, code, kind, source: failure.source, message: failure.message });
}
for (const item of implementation) assert.equal(hash(item.path), item.sha256);
writeFileSync(join(work, 'result.json'), JSON.stringify({ passed: true, implementation,
  positive: { output: positive.output, values: ['injected', 'injected', 'constructed', 'body'],
    files: identities(generated.map(name => join(positive.output, `${name}.ets`))) }, failures,
  declarationIdentity: 'symbol + generic arity + receivers + parameter types + declaration return type',
  genericReturnKey: 'resolved source return type + target return type',
}, null, 2));
console.log(`PASS project adapter identity, generic returns, overloads, body priority and five classified failures`);
console.log(`Evidence: ${work}`);
