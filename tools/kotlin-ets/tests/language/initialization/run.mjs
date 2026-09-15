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
const sources = ['Trace.kt', 'Model.kt', 'Dependency.kt', 'Values.kt', 'Failure.kt', 'OuterFailure.kt', 'Consumer.kt',
  '../globals/Initialized.kt'].map(name => join(here, name));
const inputs = [...readdirSync(join(root, 'src'), { recursive: true }).filter(p => p.endsWith('.kt')).map(p => join(root, 'src', p)),
  ...sources, join(here, 'Oracle.kt'), fileURLToPath(import.meta.url)].map(path => ({ path, sha256: hash(path) }));
const result = { inputs, commands: [], passed: false, level: 'JVM/ETS host; not SDK/native' };
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
const scenarios = ['method', 'property', 'write', 'default', 'failure', 'nestedFailure'];
result.expected = Object.fromEntries(scenarios.map(scenario => [scenario,
  run('jvm-' + scenario, 'java', ['-cp', `${jar}:${cp}`, 'initialization.OracleKt', scenario]).trim().split('\n')]));
const flat = join(work, 'Initialization.ets'), modules = join(work, 'modules'), reversed = join(work, 'reversed');
run('flat', 'bash', [cli, '--mode', 'language', '--out', flat, ...sources]);
run('modules', 'bash', [cli, '--mode', 'language', '--out-dir', modules, ...sources]);
run('reversed', 'bash', [cli, '--mode', 'language', '--out-dir', reversed, ...sources.toReversed()]);
const names = readdirSync(modules).sort();
assert.deepEqual(names, readdirSync(reversed).sort());
for (const name of names) assert.equal(readFileSync(join(modules, name), 'utf8'), readFileSync(join(reversed, name), 'utf8'));
const options = { strict: true, noEmit: true, target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, types: [] };
const files = [flat, ...names.map(p => join(modules, p))];
const typed = files.map(path => { const target = path.replace(/\.ets$/, '.ts'); writeFileSync(target, readFileSync(path)); return target; });
assert.deepEqual(ts.getPreEmitDiagnostics(ts.createProgram(typed, options)).map(d => ts.flattenDiagnosticMessageText(d.messageText, '\n')), []);
function evaluate(entry, scenario) {
  const cache = new Map();
  const context = vm.createContext({});
  function load(path) {
    if (cache.has(path)) return cache.get(path);
    const exports = {}; cache.set(path, exports);
    const code = ts.transpileModule(readFileSync(path, 'utf8'), { compilerOptions: options }).outputText;
    vm.runInContext(`(function(exports, require) {\n${code}\n})`, context, { timeout: 1000 })(
      exports, name => load(resolve(dirname(path), name + '.ets')));
    return exports;
  }
  const e = load(entry), values = [e.before()];
  if (scenario === 'failure' || scenario === 'nestedFailure') {
    for (let n = 0; n < 2; n++) {
      try { values.push(String(scenario === 'failure' ? e.readFailure() : e.readOuterFailure())); }
      catch (failure) { values.push(failure.name); }
      values.push(e.before());
    }
  } else {
    values.push(scenario === 'method' ? e.methodFirst() : scenario === 'property' ? e.propertyFirst()
      : scenario === 'default' ? e.defaultFirst() : e.writeFirst(8));
    values.push(e.methodFirst(), e.writeFirst(3), e.propertyFirst(), e.legacyInitializer());
  }
  return values;
}
result.actual = Object.fromEntries(scenarios.map(s => [s, evaluate(flat, s)]));
result.moduleActual = Object.fromEntries(scenarios.map(s => [s, evaluate(join(modules, 'Consumer.ets'), s)]));
assert.deepEqual(result.actual, result.expected); assert.deepEqual(result.moduleActual, result.expected);
for (const input of inputs) assert.equal(hash(input.path), input.sha256);
result.outputs = files.map(path => ({ path, sha256: hash(path) })); result.passed = true; record();
console.log('PASS first-use method/read/write, owner and cross-file order, objects/lists, once-only effects and sticky initialization failure; flat + modules');
