import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';

const here = dirname(fileURLToPath(import.meta.url)), root = resolve(here, '../../..');
mkdirSync(join(here, '.work'), { recursive: true });
const work = mkdtempSync(join(here, '.work/run-'));
console.log(`Evidence: ${work}`);
const hash = path => createHash('sha256').update(readFileSync(path)).digest('hex');
const sources = ['Model.kt', 'Selection.kt', 'Application.kt', 'Queries.kt'].map(name => join(here, name));
const inputs = [...readdirSync(join(root, 'src'), { recursive: true }).filter(p => p.endsWith('.kt')).map(p => join(root, 'src', p)),
  ...sources, join(here, 'Oracle.kt'), join(here, 'NonLocal.kt'), fileURLToPath(import.meta.url)].map(path => ({ path, sha256: hash(path) }));
const result = { inputs, commands: [], passed: false, level: 'JVM/ETS host; not SDK or native' };
const record = () => writeFileSync(join(work, 'result.json'), JSON.stringify(result, null, 2));
function run(label, command, args, status = 0) {
  const r = spawnSync(command, args, { encoding: 'utf8', timeout: 600000, maxBuffer: 16 * 1024 * 1024,
    env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' } });
  for (const stream of ['stdout', 'stderr']) writeFileSync(join(work, `${label}.${stream}`), r[stream] ?? '');
  result.commands.push({ label, command, args, status: r.status }); record();
  assert.equal(r.error, undefined); assert.equal(r.status, status, r.stdout + r.stderr); return r.stdout;
}
const compiler = join(root, 'tests/stdlib/compiler.sh'), cli = join(root, 'kotlin-ets');
const cp = run('classpath', 'bash', [compiler, '--classpath']).trim(), jar = join(work, 'oracle.jar');
run('jvm-build', 'bash', [compiler, ...sources, join(here, 'Oracle.kt'), '-d', jar]);
result.expected = run('jvm', 'java', ['-cp', `${jar}:${cp}`, 'models.OracleKt']).trim().split('\n');
assert.equal(result.expected.length, 70);
const flat = join(work, 'Models.ets'), modules = join(work, 'modules'), reversed = join(work, 'reversed');
run('flat', 'bash', [cli, '--mode', 'language', '--out', flat, ...sources]);
run('modules', 'bash', [cli, '--mode', 'language', '--out-dir', modules, ...sources]);
run('reversed', 'bash', [cli, '--mode', 'language', '--out-dir', reversed, ...sources.toReversed()]);
const moduleNames = readdirSync(modules).sort();
assert.deepEqual(moduleNames, readdirSync(reversed).sort());
for (const name of moduleNames) assert.equal(readFileSync(join(modules, name), 'utf8'), readFileSync(join(reversed, name), 'utf8'));
const options = { strict: true, noEmit: true, target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, types: [] };
const files = [flat, ...moduleNames.map(p => join(modules, p))];
const typed = files.map(path => { const target = path.replace(/\.ets$/, '.ts'); writeFileSync(target, readFileSync(path)); return target; });
assert.deepEqual(ts.getPreEmitDiagnostics(ts.createProgram(typed, options)).map(d => ts.flattenDiagnosticMessageText(d.messageText, '\n')), []);
function evaluate(entry) {
  const cache = new Map();
  function load(path) {
    if (cache.has(path)) return cache.get(path);
    const exports = {}; cache.set(path, exports);
    const code = ts.transpileModule(readFileSync(path, 'utf8'), { compilerOptions: options }).outputText;
    vm.runInNewContext(code, { exports, require: name => load(resolve(dirname(path), name + '.ets')) }, { timeout: 1000 });
    return exports;
  }
  const e = load(entry), queries = entry === flat ? e : load(join(modules, 'Queries.ets'));
  const values = [queries.emptinessCheck(false), queries.emptinessCheck(true), queries.evaluationOrder(),
    queries.nullableLet(null), queries.nullableLet(''), queries.nullableLet('Title'),
    queries.guardedGeneric(null), queries.guardedGeneric('Title'), queries.nullableGeneric(null), queries.nullableGeneric('Title')];
  for (const minimum of [-1, 0, 2, 3, 7]) for (const extra of [-2, 0, 3]) for (const pick of [false, true])
    values.push(e.scenario(minimum, extra, pick), e.afterAdjustment(2));
  return values;
}
result.actual = evaluate(flat); result.moduleActual = evaluate(join(modules, 'Application.ets'));
assert.deepEqual(result.actual, result.expected); assert.deepEqual(result.moduleActual, result.expected);
const app = ts.createSourceFile('Application.ts', readFileSync(join(modules, 'Application.ets'), 'utf8'), ts.ScriptTarget.Latest, true);
for (const [name, parameters] of [['scenario', ['minimum', 'extra', 'pick']], ['afterAdjustment', ['extra']]]) {
  const fn = app.statements.find(node => ts.isFunctionDeclaration(node) && node.name?.text === name);
  assert.ok(fn, name); assert.deepEqual(fn.parameters.map(p => p.name.getText(app)), parameters);
}
const model = ts.createSourceFile('Model.ts', readFileSync(join(modules, 'Model.ets'), 'utf8'), ts.ScriptTarget.Latest, true);
const card = model.statements.find(node => ts.isClassDeclaration(node) && node.name?.text === 'Card');
assert.ok(card);
for (const [name, parameters] of [['adjusted', ['extra']], ['display', []]]) {
  const method = card.members.find(node => ts.isMethodDeclaration(node) && node.name.getText(model) === name);
  assert.ok(method); assert.deepEqual(method.parameters.map(p => p.name.getText(model)), parameters);
}
const negative = join(here, 'NonLocal.kt'), rejectedOutput = join(work, 'NonLocal.ets');
run('nonlocal-jvm', 'bash', [compiler, negative, '-d', join(work, 'nonlocal.jar')]);
result.negative = JSON.parse(run('nonlocal', 'bash', [cli, '--mode', 'language', '--out', rejectedOutput, negative], 2));
assert.equal(result.negative.code, 'UNSUPPORTED');
assert.match(result.negative.message, /Non-local return is outside the first language slice/);
assert.equal(result.negative.source.file, negative); assert.ok(result.negative.source.line > 0);
assert.equal(existsSync(rejectedOutput), false);
for (const input of inputs) assert.equal(hash(input.path), input.sha256);
result.modules = files.map(path => ({ path, sha256: hash(path) })); result.passed = true; record();
console.log(`PASS ${result.actual.length} flat + module JVM/host nullable-model/collection results and original entry parameters; SDK/native not run`);
