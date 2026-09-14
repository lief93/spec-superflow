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
const hash = path => createHash('sha256').update(readFileSync(path)).digest('hex');
function files(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap(entry => entry.isDirectory()
    ? files(join(directory, entry.name)) : [join(directory, entry.name)]).sort();
}
const inputs = [...files(join(root, 'src')), ...readdirSync(here).filter(name => name.endsWith('.kt')).map(name => join(here, name)),
  fileURLToPath(import.meta.url)].map(path => ({ path, sha256: hash(path) }));
const env = { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' };
const commandCwd = process.cwd();
const result = { inputs, commands: [], JAVA_TOOL_OPTIONS: env.JAVA_TOOL_OPTIONS };
const record = () => writeFileSync(join(work, 'result.json'), JSON.stringify(result, null, 2));
function run(label, command, args, expectedStatus = 0) {
  const value = spawnSync(command, args, { cwd: commandCwd, env, encoding: 'utf8', timeout: 600000, maxBuffer: 16 * 1024 * 1024 });
  writeFileSync(join(work, label + '.stdout'), value.stdout ?? '');
  writeFileSync(join(work, label + '.stderr'), value.stderr ?? '');
  result.commands.push({ label, command, args, cwd: commandCwd, status: value.status }); record();
  assert.equal(value.error, undefined);
  assert.equal(value.status, expectedStatus, value.stdout + value.stderr);
  return value;
}
function identifiesInput(stderr, input) {
  const paths = [...stderr.matchAll(/^(.+\.kt):\d+:\d+: error:/gm)]
    .map(match => resolve(commandCwd, match[1]));
  return paths.includes(resolve(commandCwd, input));
}
record();
const compiler = join(root, 'tests/stdlib/compiler.sh'), source = join(here, 'Nullability.kt');
const cp = run('classpath', 'bash', [compiler, '--classpath']).stdout.trim(), jar = join(work, 'oracle.jar');
run('jvm-build', 'bash', [compiler, source, join(here, 'JvmOracle.kt'), '-d', jar]);
result.expected = run('jvm-run', 'java', ['-cp', `${jar}:${cp}`, 'nullabilityfixture.JvmOracleKt']).stdout.trimEnd().split('\n');
const output = join(work, 'Nullability.ets');
run('public-cli', 'bash', [join(root, 'kotlin-ets'), '--mode', 'language', '--out', output, source]);
const code = readFileSync(output, 'utf8');
const tree = ts.createSourceFile(output, code, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
assert.deepEqual(tree.parseDiagnostics, []);
for (const [name, parameters] of [['positive', ['value']], ['safeLength', ['value']], ['elvisInt', ['value', 'fallback']],
  ['safeString', ['value']], ['safeEffects', ['value']], ['guardEffects', ['value']],
  ['assignedInt', ['value']], ['sourceReceiver', ['value']]]) {
  const declaration = tree.statements.find(node => ts.isFunctionDeclaration(node) && node.name.text === name);
  assert.ok(declaration, name);
  assert.deepEqual(declaration.parameters.map(parameter => parameter.name.text), parameters);
}
const compiled = ts.transpileModule(code, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS }, reportDiagnostics: true });
assert.deepEqual(compiled.diagnostics, []);
const context = vm.createContext({ exports: {} });
vm.runInContext(compiled.outputText, context, { timeout: 1000 });
result.cases = [];
for (const value of [null, -1, 0, 1, -2147483648, 2147483647]) {
  for (const name of ['positive', 'elvisInt', 'nonNullElse', 'assignedInt', 'receiverCase', 'elvisEffects', 'guardEffects']) {
    result.cases.push({ name, args: name === 'elvisInt' ? [value, 7] : [value] });
  }
}
for (const value of [null, '', 'abc']) {
  for (const name of ['optionalLength', 'safeLength', 'safeString', 'nonEmpty', 'safeEffects']) {
    result.cases.push({ name, args: [value] });
  }
}
result.actual = result.cases.map(({ name, args }) => String(vm.runInContext(
  `exports.${name}(${args.map(value => JSON.stringify(value)).join(',')})`, context, { timeout: 1000 })));
record();
assert.equal(result.expected.length, 57);
assert.deepEqual(result.actual, result.expected);
for (const name of ['InvalidComparison', 'InvalidReceiver', 'InvalidGuardScope']) {
  const input = join(here, name + '.kt'), rejectedJar = join(work, name + '.jar'), rejectedOutput = join(work, name + '.ets');
  const jvm = run(name + '-jvm', 'bash', [compiler, input, '-d', rejectedJar], 1);
  assert.ok(identifiesInput(jvm.stderr, input), 'JVM rejection must identify the original input');
  assert.equal(existsSync(rejectedJar), false);
  const cli = run(name + '-cli', 'bash', [join(root, 'kotlin-ets'), '--mode', 'language', '--out', rejectedOutput, input], 1);
  const diagnostic = JSON.parse(cli.stdout);
  assert.equal(diagnostic.code, 'COMPILATION_REJECTED');
  assert.ok(identifiesInput(cli.stderr, input), 'CLI frontend rejection must identify the original input');
  assert.equal(existsSync(rejectedOutput), false);
}
for (const input of inputs) assert.equal(hash(input.path), input.sha256, `Changed during verification: ${input.path}`);
result.output = { path: output, sha256: hash(output) }; result.passed = true; record();
console.log(`PASS ${result.actual.length} same-input JVM/host nullable-flow cases; 3 original-source JVM/CLI rejection boundaries`);
