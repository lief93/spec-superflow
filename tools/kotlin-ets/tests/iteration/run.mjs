import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';

const here = dirname(fileURLToPath(import.meta.url)), root = resolve(here, '../..');
mkdirSync(join(here, '.work'), { recursive: true });
const work = mkdtempSync(join(here, '.work/run-'));
console.log(`Evidence: ${work}`);
const env = { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' };
const hash = path => createHash('sha256').update(readFileSync(path)).digest('hex');
function identities(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap(entry => {
    const path = join(directory, entry.name);
    return entry.isDirectory() ? identities(path) : [{ path, sha256: hash(path) }];
  });
}
const source = join(here, 'Iteration.kt');
const manifest = { implementation: identities(join(root, 'src')), env,
  inputs: [source, join(here, 'JvmOracle.kt')].map(path => ({ path, sha256: hash(path) })), commands: [] };
// Only retain the requested JVM settings, not unrelated host environment values.
manifest.env = { JAVA_TOOL_OPTIONS: env.JAVA_TOOL_OPTIONS };
function record() { writeFileSync(join(work, 'result.json'), JSON.stringify(manifest, null, 2)); }
function run(label, command, args, expectedStatus = 0) {
  const result = spawnSync(command, args, { encoding: 'utf8', timeout: 600000, maxBuffer: 16 * 1024 * 1024, env });
  writeFileSync(join(work, label + '.stdout'), result.stdout ?? '');
  writeFileSync(join(work, label + '.stderr'), result.stderr ?? '');
  manifest.commands.push({ label, command, args, status: result.status, error: result.error?.message });
  record();
  assert.equal(result.error, undefined);
  assert.equal(result.status, expectedStatus, `${label}: ${result.stdout}\n${result.stderr}`);
  return result.stdout;
}
record();
const compiler = join(root, 'tests/stdlib/compiler.sh');
const cp = run('classpath', 'bash', [compiler, '--classpath']).trim();
const jar = join(work, 'oracle.jar');
run('jvm-build', 'bash', [compiler, source, join(here, 'JvmOracle.kt'), '-d', jar]);
manifest.expected = run('jvm-run', 'java', ['-cp', `${jar}:${cp}`, 'iterationfixture.JvmOracleKt']).trimEnd().split('\n');
const output = join(work, 'Iteration.ets');
run('public-cli', 'bash', [join(root, 'kotlin-ets'), '--mode', 'language', '--out', output, source]);
const code = readFileSync(output, 'utf8');
const syntax = ts.createSourceFile(output, code, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
assert.deepEqual(syntax.parseDiagnostics, []);
const functions = syntax.statements.filter(ts.isFunctionDeclaration);
for (const [name, parameters] of [['listValues', ['values']], ['copied', ['values']], ['composed', ['first', 'last', 'stride']]]) {
  const declaration = functions.find(node => node.name.text === name);
  assert.ok(declaration, name);
  assert.deepEqual(declaration.parameters.map(parameter => parameter.name.text), parameters);
}
const compiled = ts.transpileModule(code, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS }, reportDiagnostics: true });
assert.deepEqual(compiled.diagnostics, []);
const context = vm.createContext({ exports: {} });
vm.runInContext(compiled.outputText, context, { timeout: 1000 });
const min = -2147483648, max = 2147483647;
const cases = [
  ['listValues', [[]]], ['listValues', [[1, -2, 3]]], ['iterableValues', [[min, 0, max]]],
  ['copied', [['a', 'b']], '.join(",")'], ['arrayValues', [[1, 2, 3]]], ['arrayValues', [[]]],
  ['copiedArray', [['c', 'd']], '.join(",")'],
  ['primitiveValues', [[min, max]]], ['constructors', [3]], ['constructors', [max]],
  ['arrayReplacement', [[1, 2, 3]]], ['arrayReplacement', [[]]], ['listCaptures', [[-1, 0, 2]]],
  ['listCaptures', [[]]], ['arrayCaptures', [[7, 8]]], ['nestedJumps', [[-1, 0, 1, 2, 3]]],
  ['evaluatedList', [[3, 4]]], ['evaluatedList', [[]]], ['sharedCapture', [[-1, 2, 3]]],
  ['sharedCapture', [[max, 1]]], ['modifiedList', [3]], ['modificationThenBreak', [3]],
  ['iteratorNext', [[]]], ['iteratorNext', [[5]]], ['mutableIteratorNext', [[]]], ['mutableIteratorNext', [[6]]],
  ['iteratorScenario', [[]]], ['iteratorScenario', [[5]]], ['iteratorScenario', [[5, 6]]],
  ['progressionNext', [min, max]], ['progressionNext', [2, 1]], ['composed', [-3, 5, 2]],
  ['composed', [5, -3, 2]], ['composed', [min, min, 1]], ['composed', [min, max, max]],
  ['storedProgression', [min, max, max]], ['storedProgression', [max, max, 2]],
  ['reversedProgression', [9, -2, 3]], ['reversedProgression', [max, min, max]], ['reversedProgression', [1, 3, 2]],
  ['repeatedStep', [0, 10, 4, 3]], ['repeatedStep', [0, 10, 4, 0]],
];
manifest.actual = cases.map(([name, args, suffix = '']) => {
  try { return String(vm.runInContext(`exports.${name}(${args.map(arg => JSON.stringify(arg)).join(',')})${suffix}`, context, { timeout: 1000 })); }
  catch (failure) { return failure.message; }
});
for (const args of [[-2, 5, 2], [5, -2, 2], [5, -2, 0], [0, min, 1], [0, min, -1]]) {
  vm.runInContext('var effects = new exports.IterationEffects();', context);
  try { manifest.actual.push(vm.runInContext(`exports.evaluatedProgression(effects,${args.join(',')})`, context, { timeout: 1000 })); }
  catch (failure) { manifest.actual.push(failure.message + '|' + context.effects.trace); }
}
record();
assert.deepEqual(manifest.actual, manifest.expected);
for (const name of ['UnsupportedSequence', 'UnsupportedCustom']) {
  const path = join(here, name + '.kt'), out = join(work, name + '.ets');
  manifest.inputs.push({ path, sha256: hash(path) });
  const diagnostic = JSON.parse(run(name, 'bash', [join(root, 'kotlin-ets'), '--mode', 'language', '--out', out, path], 2));
  assert.equal(diagnostic.code, 'UNSUPPORTED');
  assert.equal(diagnostic.source.file, path);
  assert.ok(diagnostic.source.start >= 0 && diagnostic.source.end > diagnostic.source.start);
  assert.equal(existsSync(out), false);
}
const typeOnly = join(here, 'TypeOnly.kt');
manifest.inputs.push({ path: typeOnly, sha256: hash(typeOnly) });
const typeOutput = join(work, 'TypeOnly.ets');
run('type-only', 'bash', [join(root, 'kotlin-ets'), '--mode', 'language', '--out', typeOutput, typeOnly]);
const typeSyntax = ts.createSourceFile(typeOutput, readFileSync(typeOutput, 'utf8'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
assert.deepEqual(typeSyntax.parseDiagnostics, []);
for (const name of ['__etsIterator', '__etsIntProgression']) {
  assert.equal(typeSyntax.statements.filter(node => ts.isClassDeclaration(node) && node.name.text === name).length, 1);
}
manifest.output = output;
manifest.outputSha256 = hash(output);
for (const input of [...manifest.implementation, ...manifest.inputs]) assert.equal(hash(input.path), input.sha256, `Changed during verification: ${input.path}`);
manifest.passed = true;
record();
console.log(`PASS ${manifest.actual.length} same-source JVM/host iteration cases; type-only runtime closure and 2 source-linked unsupported boundaries`);
