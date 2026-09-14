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
const work = mkdtempSync(join(here, '.work/probe-'));
console.log(`Evidence: ${work}`);
const implementationRoot = process.env.KOTLIN_ETS_SOURCE_ROOT ?? join(root, 'src');
const implementations = readdirSync(implementationRoot, { recursive: true }).filter(path => path.endsWith('.kt'))
  .map(path => join(implementationRoot, path)).sort();
const source = join(here, 'BoundedReceivers.kt'), probe = join(here, 'BoundedReceiverProbe.kt');
const fixtures = readdirSync(here).filter(name => name.endsWith('.kt')).map(name => join(here, name));
const hash = path => createHash('sha256').update(readFileSync(path)).digest('hex');
const result = { inputs: [...implementations, ...fixtures, fileURLToPath(import.meta.url)].map(path => ({ path, sha256: hash(path) })), commands: [] };
const record = () => writeFileSync(join(work, 'result.json'), JSON.stringify(result, null, 2));
const cwd = process.cwd(), env = { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' };
function run(label, command, args, status = 0) {
  const value = spawnSync(command, args, { cwd, env, encoding: 'utf8', timeout: 600000, maxBuffer: 16 * 1024 * 1024 });
  writeFileSync(join(work, label + '.stdout'), value.stdout ?? '');
  writeFileSync(join(work, label + '.stderr'), value.stderr ?? '');
  result.commands.push({ label, command, args, cwd, status: value.status }); record();
  assert.equal(value.error, undefined);
  assert.equal(value.status, status, value.stdout + value.stderr);
  return value;
}
const compiler = join(root, 'tests/stdlib/compiler.sh');
const cp = run('classpath', 'bash', [compiler, '--classpath']).stdout.trim(), jar = join(work, 'probe.jar');
run('compile', 'bash', [compiler, ...implementations, probe, '-d', jar]);
console.log(run('probe', 'java', ['-cp', `${jar}:${cp}`, 'dev.ets.BoundedReceiverProbeKt', source, cp, work]).stdout.trim());
const oracle = join(work, 'oracle.jar');
run('oracle-build', 'bash', [compiler, source, join(here, 'JvmOracle.kt'), '-d', oracle]);
result.expected = run('oracle', 'java', ['-cp', `${oracle}:${cp}`, 'boundedreceivers.JvmOracleKt']).stdout.trimEnd().split('\n');
const output = join(work, 'BoundedReceivers.ets');
const compiled = ts.transpileModule(readFileSync(output, 'utf8'), {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS }, reportDiagnostics: true,
});
assert.deepEqual(compiled.diagnostics, []);
const context = vm.createContext({ exports: {} });
vm.runInContext(compiled.outputText, context, { timeout: 1000 });
result.actual = [];
for (const seed of [0, -3, 7, -2147483648, 2147483647]) {
  for (const name of ['interfaceCase', 'classCase', 'plainCase', 'ancestorCase', 'chainCase', 'identityCase', 'selfCase', 'orderCase']) {
    result.actual.push(String(vm.runInContext(`exports.${name}(${seed})`, context, { timeout: 1000 })));
  }
}
record(); assert.equal(result.expected.length, 40); assert.deepEqual(result.actual, result.expected);
// Migrated only after unchanged-input R2C focused and public proof (public-QGPUk6).
const supported = join(here, 'SupportedGenericMember.kt'), supportedOut = join(work, 'SupportedGenericMember.ets');
run('supported-generic-member', 'java', ['-cp', `${jar}:${cp}`, 'dev.ets.MainKt', '--mode', 'language', '--classpath', cp,
  '--out', supportedOut, supported]);
assert.ok(existsSync(supportedOut));
// Reuse this compiled production entry point for focused negatives, not a public launcher claim.
for (const input of fixtures.filter(path => path.includes('/Unsupported'))) {
  const name = input.slice(input.lastIndexOf('/') + 1), out = join(work, name + '.ets');
  if (name === 'UnsupportedVariance.kt') {
    run(name, 'java', ['-cp', `${jar}:${cp}`, 'dev.ets.MainKt', '--mode', 'language', '--classpath', cp, '--out', out, input]);
    const js = ts.transpileModule(readFileSync(out, 'utf8'), { compilerOptions: {
      target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } }).outputText;
    assert.equal(vm.runInNewContext(js + '\nvariant({ read() { return 7; } })', { exports: {} }, { timeout: 1000 }), 7);
    continue;
  }
  const value = run(name, 'java', ['-cp', `${jar}:${cp}`, 'dev.ets.MainKt', '--mode', 'language', '--classpath', cp, '--out', out, input], 2);
  const diagnostic = JSON.parse(value.stdout);
  assert.equal(diagnostic.code, 'UNSUPPORTED');
  assert.equal(diagnostic.source.file, input);
  assert.ok(diagnostic.source.start >= 0 && diagnostic.source.end > diagnostic.source.start);
  assert.equal(existsSync(out), false);
}
const invalid = join(here, 'InvalidBoundCycle.kt'), rejectedJar = join(work, 'invalid.jar'), rejectedEts = join(work, 'invalid.ets');
function identifiesInput(stderr) {
  return [...stderr.matchAll(/^(.+\.kt):\d+:\d+: error:/gm)].some(match => resolve(cwd, match[1]) === invalid);
}
const invalidJvm = run('cycle-jvm', 'bash', [compiler, invalid, '-d', rejectedJar], 1);
assert.ok(identifiesInput(invalidJvm.stderr)); assert.equal(existsSync(rejectedJar), false);
const invalidTarget = run('cycle-frontend', 'java', ['-cp', `${jar}:${cp}`, 'dev.ets.MainKt', '--mode', 'language', '--classpath', cp, '--out', rejectedEts, invalid], 1);
assert.equal(JSON.parse(invalidTarget.stdout).code, 'COMPILATION_REJECTED');
assert.ok(identifiesInput(invalidTarget.stderr)); assert.equal(existsSync(rejectedEts), false);
for (const input of result.inputs) assert.equal(hash(input.path), input.sha256, `Changed during verification: ${input.path}`);
result.output = { path: output, sha256: hash(output) };
result.passed = true; record();
console.log('PASS focused 40 same-input JVM/host cases, generic-member and unchanged variance positives, two source-linked negatives and JVM/frontend cycle rejection; not a public launcher or SDK run');
