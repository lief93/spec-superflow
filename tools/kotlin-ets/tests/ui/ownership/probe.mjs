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
const work = mkdtempSync(join(here, '.work/probe-'));
console.log(`Evidence: ${work}`);
const sourceFiles = ['Widgets.kt', 'Screen.kt', 'Services.kt'].map(name => join(here, name));
const implementationRoot = process.env.KOTLIN_ETS_SOURCE_ROOT ?? join(root, 'src');
const implementations = readdirSync(implementationRoot, { recursive: true }).filter(path => path.endsWith('.kt'))
  .map(path => join(implementationRoot, path)).sort();
const hash = path => createHash('sha256').update(readFileSync(path)).digest('hex');
const inputs = [...implementations, ...sourceFiles, join(here, 'OwnershipProbe.kt'), join(here, 'JvmOracle.kt')]
  .map(path => ({ path, sha256: hash(path) }));
const result = { inputs, commands: [] };
const record = () => writeFileSync(join(work, 'result.json'), JSON.stringify(result, null, 2));
const env = { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' };
function run(label, command, args) {
  const value = spawnSync(command, args, { env, encoding: 'utf8', timeout: 600000, maxBuffer: 16 * 1024 * 1024 });
  writeFileSync(join(work, label + '.stdout'), value.stdout ?? '');
  writeFileSync(join(work, label + '.stderr'), value.stderr ?? '');
  result.commands.push({ label, command, args, status: value.status }); record();
  assert.equal(value.error, undefined);
  assert.equal(value.status, 0, value.stdout + value.stderr);
  return value.stdout.trim();
}
const compiler = join(root, 'tests/stdlib/compiler.sh');
const cp = run('classpath', 'bash', [compiler, '--classpath']);
const uiCp = JSON.parse(readFileSync(join(process.env.KOTLIN_ETS_PROBE ?? '/tmp/kotlin-official-frontend-probe-06', 'classpath.json'))).join(':');
const jar = join(work, 'probe.jar');
run('compile', 'bash', [compiler, ...implementations, join(here, 'OwnershipProbe.kt'), '-d', jar]);
console.log(run('probe', 'java', ['-cp', `${jar}:${cp}`, 'dev.ets.OwnershipProbeKt', uiCp, work, ...sourceFiles]));
const oracle = join(work, 'oracle.jar');
run('oracle-build', 'bash', [compiler, join(here, 'Services.kt'), join(here, 'JvmOracle.kt'), '-d', oracle]);
result.expected = run('oracle', 'java', ['-cp', `${oracle}:${cp}`, 'ownership.JvmOracleKt']).split('\n');
const compiled = ts.transpileModule(readFileSync(join(work, 'helpers.ts'), 'utf8'), {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS }, reportDiagnostics: true,
});
assert.deepEqual(compiled.diagnostics, []);
const context = vm.createContext({ exports: {} });
vm.runInContext(compiled.outputText, context, { timeout: 1000 });
result.actual = [0, -3, 7, -2147483648, 2147483647].map(seed => String(vm.runInContext(`exports.replay(${seed})`, context)));
assert.deepEqual(result.actual, result.expected);
for (const input of inputs) assert.equal(hash(input.path), input.sha256, `Changed during verification: ${input.path}`);
result.output = { path: join(work, 'OwnershipPage.ets'), sha256: hash(join(work, 'OwnershipPage.ets')) };
result.modules = readdirSync(join(work, 'modules')).sort().map(name => {
  const path = join(work, 'modules', name);
  return { path, sha256: hash(path) };
});
result.passed = true; record();
console.log('PASS five same-input JVM/host captured-callback replay cases; source hash guard');
