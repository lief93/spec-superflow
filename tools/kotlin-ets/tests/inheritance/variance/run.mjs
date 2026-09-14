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
const implementations = readdirSync(join(root, 'src'), { recursive: true }).filter(p => p.endsWith('.kt')).map(p => join(root, 'src', p)).sort();
const fixtures = readdirSync(here).filter(p => p.endsWith('.kt')).map(p => join(here, p));
const result = { passed: false, inputs: [...implementations, ...fixtures, fileURLToPath(import.meta.url)].map(path => ({ path, sha256: hash(path) })), commands: [] };
const record = () => writeFileSync(join(work, 'result.json'), JSON.stringify(result, null, 2));
function run(label, command, args, status = 0) {
  const r = spawnSync(command, args, { encoding: 'utf8', timeout: 600000, maxBuffer: 32 * 1024 * 1024,
    env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' } });
  writeFileSync(join(work, `${label}.stdout`), r.stdout ?? '');
  writeFileSync(join(work, `${label}.stderr`), r.stderr ?? '');
  result.commands.push({ label, command, args, status: r.status }); record();
  assert.equal(r.error, undefined); assert.equal(r.status, status, r.stdout + r.stderr); return r.stdout;
}
const compiler = join(root, 'tests/stdlib/compiler.sh'), cli = join(root, 'kotlin-ets');
const originalMultiple = join(here, '../bounds/UnsupportedMultipleBounds.kt');
result.inputs.push({ path: originalMultiple, sha256: hash(originalMultiple) });
const sources = ['Models.kt', 'Cases.kt', 'Bounds.kt', 'Independent.kt', 'ClassBounds.kt', 'Projections.kt'].map(p => join(here, p)).concat(originalMultiple);
const cp = run('classpath', 'bash', [compiler, '--classpath']).trim(), jar = join(work, 'oracle.jar');
run('jvm-build', 'bash', [compiler, ...sources, join(here, 'Oracle.kt'), '-d', jar]);
result.expected = run('jvm-run', 'java', ['-cp', `${jar}:${cp}`, 'declarationvariance.OracleKt']).trimEnd().split('\n');
assert.equal(result.expected.length, 140);
const proof = join(work, 'proof.jar');
run('ir-build', 'bash', [compiler, ...implementations, join(here, 'Probe.kt'), join(here, 'SourceTypesProbe.kt'), '-d', proof]);
result.sourceTypes = run('source-types-probe', 'java', ['-cp', `${proof}:${cp}`, 'dev.ets.variance.types.SourceTypesProbeKt', cp, ...sources]);
const flat = join(work, 'Variance.ets'), modules = join(work, 'modules'), reversed = join(work, 'reversed');
run('flat', 'bash', [cli, '--mode', 'language', '--out', flat, ...sources]);
run('modules', 'bash', [cli, '--mode', 'language', '--out-dir', modules, ...sources]);
run('reversed', 'bash', [cli, '--mode', 'language', '--out-dir', reversed, ...sources.toReversed()]);
assert.deepEqual(readdirSync(modules).sort(), ['Bounds.ets', 'Cases.ets', 'ClassBounds.ets', 'Independent.ets', 'Models.ets', 'Projections.ets', 'UnsupportedMultipleBounds.ets']);
result.modules = readdirSync(modules).sort().map(name => ({ name, path: join(modules, name), sha256: hash(join(modules, name)) }));
const tsFiles = [flat, ...result.modules.map(m => m.path)].map(path => {
  const target = path.replace(/\.ets$/, '.ts'); writeFileSync(target, readFileSync(path)); return target;
});
const options = { strict: true, noEmit: true, target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, skipLibCheck: true };
assert.deepEqual(ts.getPreEmitDiagnostics(ts.createProgram(tsFiles, options)).map(d => ts.flattenDiagnosticMessageText(d.messageText, '\n')), []);
const cache = new Map();
function load(path) {
  if (cache.has(path)) return cache.get(path);
  const exports = {}; cache.set(path, exports);
  const js = ts.transpileModule(readFileSync(path, 'utf8'), { compilerOptions: options }).outputText;
  vm.runInNewContext(js, { exports, require(specifier) { assert.ok(specifier.startsWith('./')); return load(join(dirname(path), `${specifier}.ets`)); } }, { timeout: 1000 });
  return exports;
}
function evaluate(exports) {
  const context = vm.createContext({ exports });
  return [0, -3, 7, -2147483648, 2147483647].flatMap(seed =>
    ['covariance', 'contravariance', 'nested', 'property', 'mixed', 'nullable', 'broadBound', 'narrowBound', 'classBound', 'nominalBound',
      'independent', 'independentGeneric', 'independentClass', 'independentSelf', 'independentChain', 'independentDiamond', 'originalMultiple',
      'classInterface', 'interfaceClass', 'classInterfaceReturn', 'classInterfaceHolder', 'classInterfaceMutation',
      'projectedRead', 'projectedWrite', 'projectedStar', 'projectedBound', 'projectedNested'].map(name =>
      String(vm.runInContext(`exports.${name}(${seed})`, context, { timeout: 1000 }))).concat(
      String(vm.runInContext(`(() => { const cell = new exports.Cell(new exports.Specific(${seed})); return exports.project(cell) === cell; })()`, context, { timeout: 1000 }))));
}
result.actual = evaluate(load(flat)); result.moduleActual = evaluate({ ...load(join(modules, 'Cases.ets')),
  ...load(join(modules, 'Bounds.ets')), ...load(join(modules, 'Independent.ets')), ...load(join(modules, 'ClassBounds.ets')),
  ...load(join(modules, 'Projections.ets')), ...load(join(modules, 'Models.ets')) });
assert.deepEqual(result.actual, result.expected); assert.deepEqual(result.moduleActual, result.expected);
for (const { name, path } of result.modules) assert.equal(readFileSync(path, 'utf8'), readFileSync(join(reversed, name), 'utf8'));
result.ir = run('ir-probe', 'java', ['-cp', `${proof}:${cp}`, 'dev.ets.variance.ProbeKt', cp, ...sources]);
const invalidOut = join(work, 'Invalid.ets');
result.invalid = JSON.parse(run('invalid', 'bash', [cli, '--mode', 'language', '--out', invalidOut, join(here, 'Invalid.kt')], 1));
assert.equal(result.invalid.code, 'COMPILATION_REJECTED'); assert.equal(existsSync(invalidOut), false);
assert.equal((readFileSync(join(work, 'invalid.stderr'), 'utf8').match(/\[TYPE_VARIANCE_CONFLICT_ERROR\]/g) ?? []).length, 3);
const missingBound = join(work, 'InvalidIndependent.ets');
result.invalidBound = JSON.parse(run('missing-bound', 'bash', [cli, '--mode', 'language', '--out', missingBound,
  join(here, 'InvalidIndependent.kt')], 1));
assert.equal(result.invalidBound.code, 'COMPILATION_REJECTED'); assert.equal(existsSync(missingBound), false);
const invalidProjection = join(work, 'InvalidProjection.ets');
result.invalidProjection = JSON.parse(run('invalid-projection', 'bash', [cli, '--mode', 'language', '--out', invalidProjection,
  join(here, 'InvalidProjection.kt')], 1));
assert.equal(result.invalidProjection.code, 'COMPILATION_REJECTED'); assert.equal(existsSync(invalidProjection), false);
const projectionErrors = readFileSync(join(work, 'invalid-projection.stderr'), 'utf8');
for (const name of ['writeOut', 'writeStar', 'readIn', 'invariant']) assert.ok(projectionErrors.includes(`fun ${name}(`), name);
for (const input of result.inputs) assert.equal(hash(input.path), input.sha256);
result.output = { path: flat, sha256: hash(flat) }; result.passed = true; record();
console.log('PASS 140 flat + 140 module JVM/host variance/bound/projection results, deterministic seven-file output and official variance/bound/projection refusals');
