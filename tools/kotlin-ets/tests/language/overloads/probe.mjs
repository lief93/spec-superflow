import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';

assert.equal(process.env.KOTLIN_ETS_BUILD_SLOT, '1', 'Requires the main-approved exclusive focused compiler slot');
const here = dirname(fileURLToPath(import.meta.url)), root = resolve(here, '../../..');
const baseline = process.argv.includes('--baseline');
assert.ok(!baseline || process.env.KOTLIN_ETS_SOURCE_ROOT, 'Baseline requires the preserved pre-edit producer');
const implementationRoot = process.env.KOTLIN_ETS_SOURCE_ROOT ?? join(root, 'src');
const implementation = readdirSync(implementationRoot, { recursive: true }).filter(path => path.endsWith('.kt'))
  .map(path => join(implementationRoot, path)).sort();
const fixtures = readdirSync(here).filter(path => path.endsWith('.kt')).sort().map(path => join(here, path));
const hash = path => createHash('sha256').update(readFileSync(path)).digest('hex');
mkdirSync(join(here, '.work'), { recursive: true });
const work = mkdtempSync(join(here, baseline ? '.work/baseline-' : '.work/probe-'));
console.log(`Evidence: ${work}`);
const result = { phase: baseline ? 'baseline' : 'current', inputs: [...implementation, ...fixtures, fileURLToPath(import.meta.url)]
  .map(path => ({ path, sha256: hash(path) })), commands: [] };
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
const compiler = join(root, 'tests/stdlib/compiler.sh'), source = join(here, 'Overloads.kt');
const cp = run('classpath', 'bash', [compiler, '--classpath']).stdout.trim();
const oracle = join(work, 'oracle.jar');
run('original-jvm-build', 'bash', [compiler, source, join(here, 'JvmOracle.kt'), '-d', oracle]);
result.expected = run('original-jvm-run', 'java', ['-cp', `${oracle}:${cp}`, 'overloadfixture.JvmOracleKt']).stdout.trimEnd().split('\n');
assert.equal(result.expected.length, 30);
const jar = join(work, 'probe.jar');
run('compile', 'bash', [compiler, ...implementation, join(here, 'OverloadProbe.kt'), '-d', jar]);
const probe = run('probe', 'java', ['-cp', `${jar}:${cp}`, 'dev.ets.OverloadProbeKt', source, cp, work], baseline ? 1 : 0);
const output = join(work, 'Overloads.ets');
if (baseline) {
  assert.match(probe.stderr, /Overloaded source methods are outside the first language slice/);
  assert.ok(existsSync(join(work, 'actual.ir'))); assert.equal(existsSync(output), false);
} else {
  console.log(probe.stdout.trim());
  const compiled = ts.transpileModule(readFileSync(output, 'utf8'), {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS }, reportDiagnostics: true,
  });
  assert.deepEqual(compiled.diagnostics, []);
  const context = vm.createContext({ exports: {} });
  vm.runInContext(compiled.outputText, context, { timeout: 1000 });
  result.actual = [];
  for (const seed of [0, -3, 7, -2147483648, 2147483647]) {
    for (const name of ['arityCase', 'numericCase', 'memberCase', 'genericCase', 'classGenericCase', 'effectsCase']) {
      result.actual.push(String(vm.runInContext(`exports.${name}(${seed})`, context, { timeout: 1000 })));
    }
  }
  record(); assert.deepEqual(result.actual, result.expected);
  for (const input of fixtures.filter(path => /\/(Unsupported|Invalid)/.test(path))) {
    const name = input.slice(input.lastIndexOf('/') + 1), invalid = name.startsWith('Invalid');
    const accepted = ['UnsupportedOpen.kt', 'UnsupportedInherited.kt', 'UnsupportedInterface.kt'].includes(name);
    const original = join(work, name + '.jar'), out = join(work, name + '.ets');
    const jvm = run(name + '-jvm', 'bash', [compiler, input, '-d', original], invalid ? 1 : 0);
    const target = run(name + '-target', 'java', ['-cp', `${jar}:${cp}`, 'dev.ets.MainKt', '--mode', 'language', '--classpath', cp,
      '--out', out, input], invalid ? 1 : accepted ? 0 : 2);
    const diagnostic = JSON.parse(target.stdout);
    if (accepted) { assert.equal(diagnostic.ok, true); assert.equal(existsSync(out), true); continue; }
    assert.equal(existsSync(out), false);
    if (invalid) {
      assert.equal(diagnostic.code, 'COMPILATION_REJECTED'); assert.equal(existsSync(original), false);
      for (const stderr of [jvm.stderr, target.stderr]) {
        assert.ok([...stderr.matchAll(/^(.+\.kt):\d+:\d+: error:/gm)].some(match => resolve(cwd, match[1]) === input));
      }
    } else {
      assert.equal(diagnostic.code, 'UNSUPPORTED'); assert.equal(diagnostic.source.file, input);
      assert.ok(diagnostic.source.start >= 0 && diagnostic.source.end > diagnostic.source.start);
    }
  }
  result.output = { path: output, sha256: hash(output) };
}
for (const input of result.inputs) assert.equal(hash(input.path), input.sha256, `Changed during proof: ${input.path}`);
result.passed = true; record();
console.log(baseline ? 'PASS expected baseline RED: original JVM oracle succeeds, actual overload IR rejected with no target output' :
  'PASS focused overloads: 30 original JVM/host outcomes, typed binding proof and source/frontend boundaries; no public CLI or SDK claim');
