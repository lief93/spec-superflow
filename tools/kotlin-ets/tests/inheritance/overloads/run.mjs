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
function files(path) {
  return readdirSync(path, { withFileTypes: true }).flatMap(entry => entry.name === '.work' ? [] : entry.isDirectory()
    ? files(join(path, entry.name)) : [join(path, entry.name)]).sort();
}
const inputs = [...files(join(root, 'src')), ...files(here)].map(path => ({ path, sha256: hash(path) }));
const result = { inputs, commands: [], passed: false };
const record = () => writeFileSync(join(work, 'result.json'), JSON.stringify(result, null, 2));
function run(label, command, args, status = 0) {
  const r = spawnSync(command, args, { encoding: 'utf8', timeout: 600000, maxBuffer: 16 * 1024 * 1024,
    env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' } });
  writeFileSync(join(work, label + '.stdout'), r.stdout ?? ''); writeFileSync(join(work, label + '.stderr'), r.stderr ?? '');
  result.commands.push({ label, command, args, status: r.status }); record();
  assert.equal(r.error, undefined); assert.equal(r.status, status, r.stdout + r.stderr);
  return r.stdout;
}
const sources = ['Base.kt', 'Child.kt'].map(name => join(here, name));
const compiler = join(root, 'tests/stdlib/compiler.sh'), cli = join(root, 'kotlin-ets');
const cp = run('classpath', 'bash', [compiler, '--classpath']).trim(), jar = join(work, 'oracle.jar');
run('jvm-build', 'bash', [compiler, ...sources, join(here, 'Oracle.kt'), '-d', jar]);
result.expected = run('jvm', 'java', ['-cp', `${jar}:${cp}`, 'virtualoverloads.OracleKt']).trimEnd().split('\n');
const out = join(work, 'Overloads.ets');
run('flat', 'bash', [cli, '--mode', 'language', '--out', out, ...sources]);
const options = { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS };
function check(paths) {
  const program = ts.createProgram(paths, { ...options, strict: true, noEmit: true, types: [] });
  assert.deepEqual(ts.getPreEmitDiagnostics(program).map(d => ts.flattenDiagnosticMessageText(d.messageText, '\n')), []);
}
function evaluate(exports) {
  const context = vm.createContext({ exports });
  return [0, -3, 7, -2147483648, 2147483647].flatMap(seed =>
    ['dispatch', 'generic', 'defaults', 'effects', 'numeric', 'inherited'].map(name =>
      String(vm.runInContext(`exports.${name}(${seed})`, context, { timeout: 1000 }))));
}
const code = readFileSync(out, 'utf8'), flatTs = join(work, 'Overloads.ts');
writeFileSync(flatTs, code); check([flatTs]);
const context = vm.createContext({ exports: {} });
vm.runInContext(ts.transpileModule(code, { compilerOptions: options }).outputText, context, { timeout: 1000 });
result.actual = evaluate(context.exports); record(); assert.deepEqual(result.actual, result.expected);
const modules = join(work, 'modules'), reversed = join(work, 'reversed');
run('modules', 'bash', [cli, '--mode', 'language', '--out-dir', modules, ...sources]);
run('reversed', 'bash', [cli, '--mode', 'language', '--out-dir', reversed, ...sources.toReversed()]);
assert.deepEqual(readdirSync(modules).sort(), ['Base.ets', 'Child.ets']);
result.modules = readdirSync(modules).sort().map(name => ({ name, path: join(modules, name), sha256: hash(join(modules, name)) }));
for (const { name, path } of result.modules) {
  assert.equal(readFileSync(path, 'utf8'), readFileSync(join(reversed, name), 'utf8'));
  writeFileSync(path.replace('.ets', '.ts'), readFileSync(path));
}
check(result.modules.map(({ path }) => path.replace('.ets', '.ts')));
const cache = new Map();
function load(name) {
  if (cache.has(name)) return cache.get(name);
  const exports = {}; cache.set(name, exports);
  const code = ts.transpileModule(readFileSync(join(modules, name + '.ets'), 'utf8'), { compilerOptions: options }).outputText;
  vm.runInNewContext(code, { exports, require(specifier) { assert.ok(specifier.startsWith('./')); return load(specifier.slice(2)); } }, { timeout: 1000 });
  return exports;
}
result.moduleActual = evaluate(load('Child')); assert.deepEqual(result.moduleActual, result.expected);
const proof = join(work, 'proof.jar');
run('ir-build', 'bash', [compiler, ...files(join(root, 'src')).filter(path => path.endsWith('.kt')),
  join(here, 'Probe.kt'), '-d', proof]);
result.irEvidence = run('ir-proof', 'java', ['-cp', `${proof}:${cp}`, 'dev.ets.virtualoverloads.ProbeKt', cp, work, ...sources]).trim();
result.negatives = [];
for (const [name, reason] of [['External', /external inherited declarations/], ['Covariance', /covariance is not supported/],
  ['PrivateShadow', /Private method name shadowing/], ['BridgeJoin', /Virtual overload joins require separate target bridges/]]) {
  const input = join(here, 'negatives', name + '.kt'), output = join(work, name + '.ets');
  const jvmSources = [input, ...(name === 'BridgeJoin' ? [join(here, 'BridgeOracle.kt')] : [])];
  run(name + '-jvm', 'bash', [compiler, ...jvmSources, '-d', join(work, name + '.jar')]);
  if (name === 'BridgeJoin') {
    result.bridgeExpected = run('bridge-jvm-result', 'java', ['-cp', `${join(work, name + '.jar')}:${cp}`, 'BridgeOracleKt']).trim();
    assert.equal(result.bridgeExpected, 'text:x:int:7:other:a');
  }
  const diagnostic = JSON.parse(run(name, 'java', ['-cp', `${proof}:${cp}`, 'dev.ets.MainKt', '--mode', 'language',
    '--classpath', cp, '--out', output, input], 2));
  assert.equal(diagnostic.code, 'UNSUPPORTED'); assert.match(diagnostic.message, reason);
  assert.equal(diagnostic.source.file, input);
  assert.ok(diagnostic.source.start >= 0 && diagnostic.source.end > diagnostic.source.start);
  assert.equal(existsSync(output), false); result.negatives.push(diagnostic);
}
const floatSource = join(here, 'UnsupportedFloatBody.kt'), floatOut = join(work, 'FloatBody.ets');
run('float-jvm', 'bash', [compiler, floatSource, '-d', join(work, 'FloatBody.jar')]);
result.floatBoundary = JSON.parse(run('float-boundary', 'bash', [cli, '--mode', 'language', '--out', floatOut, floatSource], 2));
assert.equal(result.floatBoundary.code, 'UNSUPPORTED');
assert.match(result.floatBoundary.message, /Unsupported external call: kotlin.Double.plus/);
assert.equal(result.floatBoundary.source.file, floatSource);
assert.ok(result.floatBoundary.source.start >= 0 && result.floatBoundary.source.end > result.floatBoundary.source.start);
assert.equal(existsSync(floatOut), false);
for (const input of inputs) assert.equal(hash(input.path), input.sha256, input.path);
result.output = { path: out, sha256: hash(out) }; result.passed = true; record();
console.log(`PASS ${result.actual.length} flat + ${result.moduleActual.length} module JVM/ETS-host virtual overload results`);
