import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';

const here = dirname(fileURLToPath(import.meta.url)), root = resolve(here, '../../..');
assert.ok(process.argv[2] && process.argv[3], 'Pass current and baseline focused result.json manifests');
const focusedPath = resolve(process.argv[2]), baselinePath = resolve(process.argv[3]);
const focused = JSON.parse(readFileSync(focusedPath)), baseline = JSON.parse(readFileSync(baselinePath));
assert.equal(focused.passed, true); assert.equal(focused.phase, 'current');
assert.equal(baseline.passed, true); assert.equal(baseline.phase, 'baseline');
assert.equal(focused.expected.length, 35); assert.deepEqual(focused.expected, baseline.expected);
const hash = path => createHash('sha256').update(readFileSync(path)).digest('hex');
for (const input of focused.inputs) assert.equal(hash(input.path), input.sha256, `Changed after focused proof: ${input.path}`);
assert.equal(focused.outputs.find(it => it.name === 'Control').sha256, baseline.outputs.find(it => it.name === 'Control').sha256,
  'Previously supported control output must remain byte-identical');
mkdirSync(join(here, '.work'), { recursive: true });
const work = mkdtempSync(join(here, '.work/public-')); console.log(`Evidence: ${work}`);
const result = { focusedPath, baselinePath, focusedSha256: hash(focusedPath), baselineSha256: hash(baselinePath),
  inputs: focused.inputs, expected: focused.expected, commands: [], outputs: [] };
const record = () => writeFileSync(join(work, 'result.json'), JSON.stringify(result, null, 2));
const env = { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' };
function run(name, input) {
  const path = join(work, name + '.ets');
  const args = [join(root, 'kotlin-ets'), '--mode', 'language', '--out', path, input];
  const value = spawnSync('bash', args, { env, encoding: 'utf8', timeout: 600000, maxBuffer: 16 * 1024 * 1024 });
  writeFileSync(join(work, name + '.stdout'), value.stdout ?? '');
  writeFileSync(join(work, name + '.stderr'), value.stderr ?? '');
  result.commands.push({ command: 'bash', args, cwd: process.cwd(), status: value.status }); record();
  assert.equal(value.error, undefined); assert.equal(value.status, 0, value.stdout + value.stderr);
  result.outputs.push({ name, path, sha256: hash(path) }); record();
  return path;
}
const contexts = {};
for (const output of focused.outputs) {
  const path = run(output.name, join(here, output.name + '.kt'));
  assert.equal(hash(path), output.sha256, 'Complete public output must equal focused output');
  const compiled = ts.transpileModule(readFileSync(path, 'utf8'), {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS }, reportDiagnostics: true,
  });
  assert.deepEqual(compiled.diagnostics, []);
  const context = vm.createContext({ exports: {} });
  vm.runInContext(compiled.outputText, context, { timeout: 1000 });
  contexts[output.name] = context;
}
result.actual = [];
const cases = ['controlCase', 'interfaceCase', 'inheritedCase', 'substitutionsCase', 'constraintsCase', 'boundedCase', 'effectsCase'];
for (const seed of [0, -3, 7, -2147483648, 2147483647]) {
  for (const [index, name] of cases.entries()) {
    result.actual.push(String(vm.runInContext(`exports.${name}(${seed})`, contexts[index === 0 ? 'Control' : 'GenericMethods'], { timeout: 1000 })));
  }
}
assert.deepEqual(result.actual, result.expected);
// These sources were migrated unchanged only after public-QGPUk6 proved both original inputs.
run('previous-bounds', join(here, '../bounds/SupportedGenericMember.kt'));
run('previous-heritage', join(here, '../generic/SupportedMemberGeneric.kt'));
for (const input of focused.inputs) assert.equal(hash(input.path), input.sha256, `Changed during public proof: ${input.path}`);
result.passed = true; record();
console.log('PASS public CLI: 35 JVM/host outcomes, complete output identity, unchanged baseline control and both exact historical negatives now accepted');
