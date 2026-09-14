import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../..');
mkdirSync(join(here, '.work'), { recursive: true });
const work = mkdtempSync(join(here, '.work/run-'));
console.log(`Evidence: ${work}`);
const hash = path => createHash('sha256').update(readFileSync(path)).digest('hex');
function identities(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap(entry => {
    const path = join(directory, entry.name);
    return entry.isDirectory() ? identities(path) : [{ path, sha256: hash(path) }];
  });
}
const source = join(here, 'Loops.kt');
const manifest = { implementation: identities(join(root, 'src')),
  sourceInputs: [source, join(here, 'JvmOracle.kt')].map(path => ({ path, sha256: hash(path) })), commands: [] };
const record = () => writeFileSync(join(work, 'result.json'), JSON.stringify(manifest, null, 2));
function run(label, command, args, status = 0) {
  const result = spawnSync(command, args, { encoding: 'utf8', timeout: 600000, maxBuffer: 16 * 1024 * 1024 });
  const stdout = join(work, label + '.stdout');
  const stderr = join(work, label + '.stderr');
  writeFileSync(stdout, result.stdout ?? '');
  writeFileSync(stderr, result.stderr ?? '');
  manifest.commands.push({ label, command, args, status: result.status, error: result.error?.message, stdout, stderr });
  record();
  assert.equal(result.error, undefined);
  assert.equal(result.status, status, `${label}: ${result.stdout}\n${result.stderr}`);
  return result.stdout;
}
record();
const compiler = join(root, 'tests/stdlib/compiler.sh');
const cp = run('classpath', 'bash', [compiler, '--classpath']).trim();
const oracle = join(work, 'oracle.jar');
run('jvm-build', 'bash', [compiler, source, join(here, 'JvmOracle.kt'), '-d', oracle]);
const java = join(process.env.JAVA_HOME ?? '/Applications/Android Studio.app/Contents/jbr/Contents/Home', 'bin/java');
manifest.expected = run('jvm-run', java, ['-cp', `${oracle}:${cp}`, 'loopfixture.JvmOracleKt']).trimEnd().split('\n');
assert.equal(manifest.expected[0], '-2,-1,0,1,2,');
assert.equal(manifest.expected[1], '');
manifest.output = join(work, 'Loops.ets');
run('public-cli', 'bash', [join(root, 'kotlin-ets'), '--mode', 'language', '--out', manifest.output, source]);
const code = readFileSync(manifest.output, 'utf8');
const parsed = ts.createSourceFile(manifest.output, code, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
assert.deepEqual(parsed.parseDiagnostics, []);
const declarations = parsed.statements.filter(ts.isFunctionDeclaration);
for (const [name, parameters] of [['ascending', ['first', 'last']], ['stepped', ['first', 'last', 'stride']],
  ['capturedIterations', ['first', 'last']], ['sharedIterations', ['first', 'last']]]) {
  const declaration = declarations.find(node => node.name.text === name);
  assert.ok(declaration, `Missing original function ${name}`);
  assert.deepEqual(declaration.parameters.map(parameter => parameter.name.text), parameters);
}
const compiled = ts.transpileModule(code, { compilerOptions: {
  target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS,
}, reportDiagnostics: true });
assert.deepEqual(compiled.diagnostics, []);
const context = vm.createContext({ exports: {} });
vm.runInContext(compiled.outputText, context, { timeout: 1000 });
const min = -2147483648, max = 2147483647;
const cases = [
  ['ascending', [-2, 2]], ['ascending', [3, 1]], ['ascending', [max - 1, max]],
  ['ascending', [min, min + 1]], ['ascending', [max, max]], ['ascending', [min, min]],
  ['exclusive', [-2, 2]], ['exclusive', [2, 2]], ['exclusive', [min, min]], ['exclusive', [max - 1, max]],
  ['descending', [2, -2]], ['descending', [1, 3]], ['descending', [min + 1, min]], ['descending', [max, max]],
  ['stepped', [-7, 8, 3]], ['stepped', [2, 1, 2]], ['stepped', [min, max, max]], ['stepped', [max, max, 2]],
  ['descendingStep', [8, -7, 3]], ['descendingStep', [max, min, max]], ['descendingStep', [min, min, 2]],
  ['evaluated', [-2, 3, 2]], ['evaluated', [3, -2, 2]],
  ['nestedFlow', [-1, 4]], ['nestedFlow', [max, max]],
  ['capturedIterations', [-1, 2]], ['capturedIterations', [max - 1, max]], ['capturedIterations', [min, min + 1]],
  ['sharedIterations', [-1, 2]], ['sharedIterations', [max - 1, max]],
  ['nativeLoopClosures', [3]], ['nativeLoopClosures', [0]],
  ['nativeConditionClosure', [0]], ['nativeConditionClosure', [1]], ['nativeConditionClosure', [3]],
  ['stepped', [3, 1, 0]], ['stepped', [3, 1, -1]], ['stepped', [3, 1, min]],
];
manifest.actual = cases.map(([name, args]) => {
  try { return vm.runInContext(`exports.${name}(${args.join(',')})`, context, { timeout: 1000 }); }
  catch (failure) { return failure.message; }
});
assert.deepEqual(manifest.actual, manifest.expected);
// Retain the original RED inputs, now accepted by the iteration runtime lane.
for (const [name, invocation, expected] of [
  ['UnsupportedList', 'exports.listIteration([1, 2, 3])', 6],
  ['UnsupportedComposed', 'exports.composedProgression(0, 10, 3)', 18],
]) {
  const input = join(here, `${name}.kt`), output = join(work, `${name}.ets`);
  manifest.sourceInputs.push({ path: input, sha256: hash(input) });
  run(name, 'bash', [join(root, 'kotlin-ets'), '--mode', 'language', '--out', output, input]);
  const compiled = ts.transpileModule(readFileSync(output, 'utf8'), {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS }, reportDiagnostics: true,
  });
  assert.deepEqual(compiled.diagnostics, []);
  const accepted = vm.createContext({ exports: {} });
  vm.runInContext(compiled.outputText, accepted, { timeout: 1000 });
  assert.equal(vm.runInContext(invocation, accepted, { timeout: 1000 }), expected);
}
for (const name of ['UnsupportedLong']) {
  const input = join(here, `${name}.kt`);
  manifest.sourceInputs.push({ path: input, sha256: hash(input) });
  const output = join(work, `${name}.ets`);
  const diagnostic = JSON.parse(run(name, 'bash', [join(root, 'kotlin-ets'), '--mode', 'language', '--out', output, input], 2));
  assert.equal(diagnostic.code, 'UNSUPPORTED');
  assert.equal(diagnostic.source.file, input);
  assert.ok(diagnostic.source.start >= 0 && diagnostic.source.end > diagnostic.source.start);
  assert.equal(existsSync(output), false);
}
manifest.outputSha256 = hash(manifest.output);
for (const input of [...manifest.implementation, ...manifest.sourceInputs]) {
  assert.equal(hash(input.path), input.sha256, `Changed during verification: ${input.path}`);
}
manifest.passed = true;
record();
console.log(`PASS ${manifest.actual.length} JVM/host target loop cases, 2 former RED inputs accepted, and 1 source-linked unsupported boundary`);
