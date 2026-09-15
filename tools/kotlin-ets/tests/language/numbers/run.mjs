import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdirSync, mkdtempSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
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
const sources = ['Numbers.kt', 'Application.kt'].map(p => join(here, p));
const inputs = [...readdirSync(join(root, 'src'), { recursive: true }).filter(p => p.endsWith('.kt')).map(p => join(root, 'src', p)),
  ...sources, join(here, 'Oracle.kt'), fileURLToPath(import.meta.url)].map(path => ({ path, sha256: hash(path) }));
const result = { inputs, commands: [], passed: false, level: 'JVM/ETS host; not SDK or native' };
const record = () => writeFileSync(join(work, 'result.json'), JSON.stringify(result, null, 2));
function run(label, command, args) {
  const r = spawnSync(command, args, { encoding: 'utf8', timeout: 600000, maxBuffer: 16 * 1024 * 1024,
    env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' } });
  for (const stream of ['stdout', 'stderr']) writeFileSync(join(work, `${label}.${stream}`), r[stream] ?? '');
  result.commands.push({ label, command, args, status: r.status }); record();
  assert.equal(r.error, undefined); assert.equal(r.status, 0, r.stdout + r.stderr); return r.stdout;
}
const compiler = join(root, 'tests/stdlib/compiler.sh'), cli = join(root, 'kotlin-ets');
const cp = run('classpath', 'bash', [compiler, '--classpath']).trim(), jar = join(work, 'oracle.jar');
run('jvm-build', 'bash', [compiler, ...sources, join(here, 'Oracle.kt'), '-d', jar]);
result.expected = run('jvm', 'java', ['-cp', `${jar}:${cp}`, 'numbers.OracleKt']).trim().split('\n');
const flat = join(work, 'Numbers.ets'), modules = join(work, 'modules');
run('flat', 'bash', [cli, '--mode', 'language', '--out', flat, ...sources]);
run('modules', 'bash', [cli, '--mode', 'language', '--out-dir', modules, ...sources]);
const options = { strict: true, noEmit: true, target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, types: [] };
const files = [flat, ...readdirSync(modules).map(p => join(modules, p))];
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
  const e = load(entry), n = entry === flat ? e : load(join(modules, 'Numbers.ets'));
  const values = [];
  const emit = value => {
    const bytes = Buffer.alloc(8); bytes.writeDoubleBE(value);
    values.push(Number.isNaN(value) ? 'NaN' : bytes.toString('hex'));
  };
  for (const seed of [0, -3, 7, 16777217, 2147483647]) {
    emit(e.layoutWidth(seed)); emit(n.floatGap(seed)); emit(n.rounded(seed));
  }
  emit(n.literal()); emit(n.widened()); emit(n.effects());
  for (const value of [0, -0, -3.75, 1 / 3, 1e30, Infinity, NaN]) {
    emit(n.narrowed(value)); emit(n.integral(value)); emit(n.floatIntegral(Math.fround(value)));
    emit(n.doubleUnary(value)); emit(n.floatUnary(Math.fround(value)));
    values.push(String(n.greater(Math.fround(value), 0)), String(n.equal(value, value)));
  }
  return values;
}
result.actual = evaluate(flat); result.moduleActual = evaluate(join(modules, 'Application.ets'));
assert.deepEqual(result.actual, result.expected); assert.deepEqual(result.moduleActual, result.expected);
const tree = ts.createSourceFile(flat, readFileSync(flat, 'utf8'), ts.ScriptTarget.Latest, true);
for (const [name, params] of Object.entries({ scaledGap: ['base', 'scale', 'extra'], layoutWidth: ['base'], narrowed: ['value'] })) {
  const declaration = tree.statements.find(n => ts.isFunctionDeclaration(n) && n.name?.text === name);
  assert.deepEqual(declaration?.parameters.map(p => p.name.getText(tree)), params);
}
for (const input of inputs) assert.equal(hash(input.path), input.sha256);
result.modules = files.map(path => ({ path, sha256: hash(path) })); result.passed = true; record();
console.log(`PASS ${result.actual.length} flat + module JVM/host numeric results, source names and effects; SDK/native not run`);
