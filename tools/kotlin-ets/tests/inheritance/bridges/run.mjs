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
const original = join(here, '../overloads/negatives/BridgeJoin.kt');
const covariance = join(here, '../overloads/negatives/Covariance.kt');
const inputs = [...files(join(root, 'src')), ...files(here), original, covariance].map(path => ({ path, sha256: hash(path) }));
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
const sources = [original, covariance, ...['Cases.kt', 'FakeJoin.kt', 'CovariantCases.kt'].map(name => join(here, name))];
const compiler = join(root, 'tests/stdlib/compiler.sh'), cli = join(root, 'kotlin-ets');
const cp = run('classpath', 'bash', [compiler, '--classpath']).trim(), jar = join(work, 'oracle.jar');
run('jvm-build', 'bash', [compiler, ...sources, join(here, 'Oracle.kt'), '-d', jar]);
result.expected = run('jvm', 'java', ['-cp', `${jar}:${cp}`, 'OracleKt']).trimEnd().split('\n');
const out = join(work, 'Bridges.ets');
run('flat', 'bash', [cli, '--mode', 'language', '--out', out, ...sources]);
const options = { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS };
function check(paths) {
  const program = ts.createProgram(paths, { ...options, strict: true, noEmit: true, types: [] });
  assert.deepEqual(ts.getPreEmitDiagnostics(program).map(d => ts.flattenDiagnosticMessageText(d.messageText, '\n')), []);
}
function evaluate(exports) {
  const context = vm.createContext({ exports });
  return [0, -3, 7, -2147483648, 2147483647].flatMap(seed =>
    ['bridgeJoin', 'inheritedBridge', 'bridgeEffects', 'voidBridge', 'genericBridge', 'nullableBridge', 'fakeBridge', 'inheritedComposition', 'bareBridge',
      'covariantDispatch', 'covariantBounds', 'covariantNullable', 'covariantJoined'].map(name =>
      String(vm.runInContext(`exports.${name}(${seed})`, context, { timeout: 1000 }))));
}
const code = readFileSync(out, 'utf8'), flatTs = join(work, 'Bridges.ts');
writeFileSync(flatTs, code); check([flatTs]);
const context = vm.createContext({ exports: {} });
vm.runInContext(ts.transpileModule(code, { compilerOptions: options }).outputText, context, { timeout: 1000 });
result.actual = evaluate(context.exports); record(); assert.deepEqual(result.actual, result.expected);
const modules = join(work, 'modules'), reversed = join(work, 'reversed');
run('modules', 'bash', [cli, '--mode', 'language', '--out-dir', modules, ...sources]);
run('reversed', 'bash', [cli, '--mode', 'language', '--out-dir', reversed, ...sources.toReversed()]);
assert.deepEqual(readdirSync(modules).sort(), ['BridgeJoin.ets', 'Cases.ets', 'Covariance.ets', 'CovariantCases.ets', 'FakeJoin.ets']);
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
result.moduleActual = evaluate({ ...load('BridgeJoin'), ...load('Cases'), ...load('FakeJoin'), ...load('CovariantCases') }); assert.deepEqual(result.moduleActual, result.expected);
const proof = join(work, 'proof.jar');
run('ir-build', 'bash', [compiler, ...files(join(root, 'src')).filter(path => path.endsWith('.kt')),
  join(here, 'Probe.kt'), '-d', proof]);
result.irEvidence = run('ir-proof', 'java', ['-cp', `${proof}:${cp}`, 'dev.ets.bridges.ProbeKt', cp, work, ...sources]).trim();
const invalid = join(here, 'InvalidCovariantOverride.kt'), invalidOut = join(work, 'InvalidCovariantOverride.ets');
run('invalid-override-jvm', 'bash', [compiler, invalid, '-d', join(work, 'invalid.jar')], 1);
result.invalidOverride = JSON.parse(run('invalid-override-target', 'java', ['-cp', `${proof}:${cp}`, 'dev.ets.MainKt',
  '--mode', 'language', '--classpath', cp, '--out', invalidOut, invalid], 1));
assert.equal(result.invalidOverride.code, 'COMPILATION_REJECTED');
assert.match(readFileSync(join(work, 'invalid-override-target.stderr'), 'utf8'), /return type|subtype/i);
assert.equal(existsSync(invalidOut), false);
const bottom = join(here, 'UnsupportedBottomText.kt'), bottomOut = join(work, 'BottomText.ets');
run('bottom-jvm', 'bash', [compiler, bottom, '-d', join(work, 'bottom.jar')]);
result.bottomBoundary = JSON.parse(run('bottom-target', 'java', ['-cp', `${proof}:${cp}`, 'dev.ets.MainKt',
  '--mode', 'language', '--classpath', cp, '--out', bottomOut, bottom], 2));
assert.equal(result.bottomBoundary.code, 'UNSUPPORTED');
assert.match(result.bottomBoundary.message, /Unsupported string concatenation operand: kotlin.Nothing\?/);
assert.equal(result.bottomBoundary.source.file, bottom);
assert.ok(result.bottomBoundary.source.start >= 0 && result.bottomBoundary.source.end > result.bottomBoundary.source.start);
assert.equal(existsSync(bottomOut), false);
for (const input of inputs) assert.equal(hash(input.path), input.sha256, input.path);
result.output = { path: out, sha256: hash(out) }; result.passed = true; record();
console.log(`PASS ${result.actual.length} flat + ${result.moduleActual.length} module JVM/ETS-host bridge results`);
