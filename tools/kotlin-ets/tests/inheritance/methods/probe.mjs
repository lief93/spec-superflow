import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';

const here = dirname(fileURLToPath(import.meta.url)), root = resolve(here, '../../..');
const baseline = process.argv.includes('--baseline');
assert.ok(!baseline || process.env.KOTLIN_ETS_SOURCE_ROOT, 'Baseline requires the frozen pre-edit source snapshot');
const implementationRoot = process.env.KOTLIN_ETS_SOURCE_ROOT ?? join(root, 'src');
const implementation = readdirSync(implementationRoot, { recursive: true }).filter(path => path.endsWith('.kt'))
  .map(path => join(implementationRoot, path)).sort();
const fixtures = readdirSync(here).filter(path => path.endsWith('.kt')).sort().map(path => join(here, path));
const previous = [join(here, '../bounds/SupportedGenericMember.kt'), join(here, '../generic/SupportedMemberGeneric.kt')];
const hash = path => createHash('sha256').update(readFileSync(path)).digest('hex');
mkdirSync(join(here, '.work'), { recursive: true });
const work = mkdtempSync(join(here, baseline ? '.work/baseline-' : '.work/probe-'));
console.log(`Evidence: ${work}`);
const result = { phase: baseline ? 'baseline' : 'current', inputs: [...implementation, ...fixtures, ...previous, fileURLToPath(import.meta.url)]
  .map(path => ({ path, sha256: hash(path) })), commands: [], outputs: [] };
const record = () => writeFileSync(join(work, 'result.json'), JSON.stringify(result, null, 2));
const cwd = process.cwd(), env = { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' };
function run(label, command, args, status = 0) {
  const value = spawnSync(command, args, { cwd, env, encoding: 'utf8', timeout: 600000, maxBuffer: 16 * 1024 * 1024 });
  writeFileSync(join(work, label + '.stdout'), value.stdout ?? '');
  writeFileSync(join(work, label + '.stderr'), value.stderr ?? '');
  result.commands.push({ label, command, args, cwd, status: value.status }); record();
  assert.equal(value.error, undefined); assert.equal(value.status, status, value.stdout + value.stderr);
  return value;
}
const compiler = join(root, 'tests/stdlib/compiler.sh');
const cp = run('classpath', 'bash', [compiler, '--classpath']).stdout.trim(), jar = join(work, 'probe.jar');
run('compile', 'bash', [compiler, ...implementation, join(here, 'GenericMethodsProbe.kt'), '-d', jar]);
const oracle = join(work, 'oracle.jar');
run('oracle-build', 'bash', [compiler, join(here, 'Control.kt'), join(here, 'GenericMethods.kt'), join(here, 'JvmOracle.kt'), '-d', oracle]);
result.expected = run('oracle', 'java', ['-cp', `${oracle}:${cp}`, 'genericmethods.JvmOracleKt']).stdout.trimEnd().split('\n');
assert.equal(result.expected.length, 35);
for (const name of ['Control', 'GenericMethods']) {
  const folder = join(work, name); mkdirSync(folder);
  const value = run(name + '-probe', 'java', ['-cp', `${jar}:${cp}`, 'dev.ets.GenericMethodsProbeKt', join(here, name + '.kt'), cp, folder],
    baseline && name === 'GenericMethods' ? 1 : 0);
  if (baseline && name === 'GenericMethods') {
    assert.match(value.stderr, /Generic, extension and default-argument inherited methods are not supported/);
    assert.equal(existsSync(join(folder, name + '.ets')), false);
    assert.ok(existsSync(join(folder, 'actual.ir')));
    continue;
  }
  console.log(value.stdout.trim());
  const path = join(folder, name + '.ets');
  result.outputs.push({ name, path, sha256: hash(path) });
}
result.actual = [];
const contexts = Object.fromEntries(result.outputs.map(({ name, path }) => {
  const compiled = ts.transpileModule(readFileSync(path, 'utf8'), {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS }, reportDiagnostics: true,
  });
  assert.deepEqual(compiled.diagnostics, []);
  const context = vm.createContext({ exports: {} });
  vm.runInContext(compiled.outputText, context, { timeout: 1000 });
  return [name, context];
}));
const cases = ['controlCase', 'interfaceCase', 'inheritedCase', 'substitutionsCase', 'constraintsCase', 'boundedCase', 'effectsCase'];
for (const seed of [0, -3, 7, -2147483648, 2147483647]) {
  for (const [index, name] of cases.entries()) {
    if (baseline && index !== 0) continue;
    result.actual.push(String(vm.runInContext(`exports.${name}(${seed})`, contexts[index === 0 ? 'Control' : 'GenericMethods'], { timeout: 1000 })));
  }
}
assert.deepEqual(result.actual, baseline ? result.expected.filter((_, index) => index % 7 === 0) : result.expected);
for (const [index, input] of previous.entries()) {
  const out = join(work, `previous-${index}.ets`);
  const value = run(`previous-${index}`, 'java', ['-cp', `${jar}:${cp}`, 'dev.ets.MainKt', '--mode', 'language', '--classpath', cp,
    '--out', out, input], baseline ? 2 : 0);
  if (baseline) {
    const diagnostic = JSON.parse(value.stdout);
    assert.equal(diagnostic.code, 'UNSUPPORTED'); assert.equal(diagnostic.source.file, input);
    assert.match(diagnostic.message, /Generic, extension and default-argument inherited methods/);
    assert.equal(existsSync(out), false);
  } else assert.ok(existsSync(out));
}
if (!baseline) {
  // Keep the exact historical source; exclude it only after its mandatory positive proof.
  run('legacy-overload-positive', process.execPath, [join(here, 'overload-positive.mjs'), 'member']);
  for (const input of fixtures.filter(path => /\/(Unsupported|Invalid)/.test(path) && path !== join(here, 'UnsupportedOverload.kt'))) {
    const name = input.slice(input.lastIndexOf('/') + 1), invalid = name.startsWith('Invalid');
    const jvmOut = join(work, name + '.jar'), out = join(work, name + '.ets');
    const jvm = run(name + '-jvm', 'bash', [compiler, input, '-d', jvmOut], invalid ? 1 : 0);
    const value = run(name + '-target', 'java', ['-cp', `${jar}:${cp}`, 'dev.ets.MainKt', '--mode', 'language', '--classpath', cp,
      '--out', out, input], invalid ? 1 : 2);
    const diagnostic = JSON.parse(value.stdout);
    assert.equal(existsSync(out), false);
    if (invalid) {
      assert.equal(diagnostic.code, 'COMPILATION_REJECTED'); assert.equal(existsSync(jvmOut), false);
      for (const stderr of [jvm.stderr, value.stderr]) {
        assert.ok([...stderr.matchAll(/^(.+\.kt):\d+:\d+: error:/gm)].some(match => resolve(cwd, match[1]) === input));
      }
    } else {
      assert.equal(diagnostic.code, name === 'UnsupportedShadow.kt' ? 'INVALID_TARGET' : 'UNSUPPORTED');
      assert.equal(diagnostic.source.file, input);
      assert.ok(diagnostic.source.start >= 0 && diagnostic.source.end > diagnostic.source.start);
    }
  }
}
for (const input of result.inputs) assert.equal(hash(input.path), input.sha256, `Changed during verification: ${input.path}`);
result.passed = true; record();
console.log(baseline ? 'PASS baseline: five existing control outcomes retained, hierarchy and two previous fixtures remain RED' :
  'PASS focused: 35 JVM/host outcomes, actual IR binding proof, two exact previous inputs and closed source/frontend boundaries; not public CLI or SDK');
