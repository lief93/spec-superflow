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
  return readdirSync(path, { withFileTypes: true }).flatMap(entry => entry.isDirectory()
    ? files(join(path, entry.name)) : [join(path, entry.name)]).sort();
}
const sources = ['Provider.kt', 'Application.kt'].map(name => join(here, name));
const inputs = [...files(join(root, 'src')), ...sources, ...files(join(here, 'negatives')),
  join(here, 'Oracle.kt'), join(here, 'IrEvidence.kt'), fileURLToPath(import.meta.url)]
  .map(path => ({ path, sha256: hash(path) }));
const result = { inputs, commands: [] };
const record = () => writeFileSync(join(work, 'result.json'), JSON.stringify(result, null, 2));
function run(label, command, args, expectedStatus = 0) {
  const value = spawnSync(command, args, { encoding: 'utf8', timeout: 600000, maxBuffer: 16 * 1024 * 1024,
    env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' } });
  writeFileSync(join(work, label + '.stdout'), value.stdout ?? '');
  writeFileSync(join(work, label + '.stderr'), value.stderr ?? '');
  result.commands.push({ label, command, args, status: value.status }); record();
  assert.equal(value.error, undefined);
  assert.equal(value.status, expectedStatus, value.stdout + value.stderr);
  return value.stdout;
}
const compiler = join(root, 'tests/stdlib/compiler.sh');
const cp = run('classpath', 'bash', [compiler, '--classpath']).trim(), jar = join(work, 'oracle.jar');
run('jvm-build', 'bash', [compiler, ...sources, join(here, 'Oracle.kt'), '-d', jar]);
result.expected = run('jvm-run', 'java', ['-cp', `${jar}:${cp}`, 'defaultfixture.OracleKt']).trimEnd().split('\n');
const output = join(work, 'Defaults.ets');
run('public-cli', 'bash', [join(root, 'kotlin-ets'), '--mode', 'language', '--out', output, ...sources]);
const code = readFileSync(output, 'utf8'), typecheck = join(work, 'Defaults.ts');
writeFileSync(typecheck, code);
const checked = ts.createProgram([typecheck], { target: ts.ScriptTarget.ES2022,
  module: ts.ModuleKind.CommonJS, strict: true, noEmit: true, types: [] });
assert.deepEqual(ts.getPreEmitDiagnostics(checked).map(d => ts.flattenDiagnosticMessageText(d.messageText, '\n')), []);
const tree = ts.createSourceFile(output, code, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
assert.deepEqual(tree.parseDiagnostics, []);
const child = tree.statements.find(node => ts.isClassDeclaration(node) && node.name.text === 'DefaultChild');
assert.deepEqual(child.members.find(node => node.name?.text === 'calculate').parameters.map(node => node.name.text), ['left', 'right']);
const bridges = tree.statements.filter(node => ts.isFunctionDeclaration(node) && node.parameters[0]?.name.text === '$this');
assert.equal(bridges.length, 10);
assert.ok(bridges.every(node => node.name.text.includes('$default')));
assert.match(code, /function DefaultBase_calculate\$default\(value: number\)/, 'User names win over compiler helper names');
assert.ok(bridges.some(node => node.name.text.startsWith('DefaultBase_calculate$default_')));
assert.match(code, /return \$this\.calculate\(/, 'Defaults must dispatch virtually, not copy the user method');
assert.doesNotMatch(code, /\(\(\): [^\n]+ => \{\s*return null;/, 'Omitted constants need no IIFE');
const compiled = ts.transpileModule(code, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } });
const context = vm.createContext({ exports: {} });
vm.runInContext(compiled.outputText, context, { timeout: 1000 });
const scenarios = ['defaults', 'genericDefaults', 'closureDefaults', 'recursiveDefaults', 'nullableDefaults',
  'bitwiseDefaults', 'wideDefaults', 'heritageDefaults', 'namedEffects'];
function evaluate(context) {
  return [0, -3, 7, -2147483648, 2147483647].flatMap(seed => scenarios.map(name =>
    String(vm.runInContext(`exports.${name}(${seed})`, context, { timeout: 1000 }))));
}
result.actual = evaluate(context);
record(); assert.deepEqual(result.actual, result.expected);

const modules = join(work, 'modules'), reversed = join(work, 'reversed');
const cli = join(root, 'kotlin-ets');
run('modules', 'bash', [cli, '--mode', 'language', '--out-dir', modules, ...sources]);
run('reversed', 'bash', [cli, '--mode', 'language', '--out-dir', reversed, ...sources.toReversed()]);
assert.deepEqual(readdirSync(modules).sort(), ['Application.ets', 'Provider.ets']);
for (const name of readdirSync(modules)) {
  assert.equal(readFileSync(join(modules, name), 'utf8'), readFileSync(join(reversed, name), 'utf8'));
  writeFileSync(join(modules, name.replace('.ets', '.ts')), readFileSync(join(modules, name), 'utf8'));
}
const moduleCheck = ts.createProgram(['Application.ts', 'Provider.ts'].map(name => join(modules, name)), {
  target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, strict: true, noEmit: true, types: [] });
assert.deepEqual(ts.getPreEmitDiagnostics(moduleCheck).map(d => ts.flattenDiagnosticMessageText(d.messageText, '\n')), []);
const providerCode = readFileSync(join(modules, 'Provider.ets'), 'utf8');
assert.doesNotMatch(providerCode, /export function adjustment/, 'Private default dependencies stay file-local');
const applicationCode = readFileSync(join(modules, 'Application.ets'), 'utf8');
assert.doesNotMatch(applicationCode, /function [^\n]*\$default/, 'Default helpers belong to their provider source file');
assert.doesNotMatch(applicationCode, /import[^\n]*adjustment/);
const cache = new Map();
function load(name) {
  if (cache.has(name)) return cache.get(name);
  const exports = {}; cache.set(name, exports);
  const code = ts.transpileModule(readFileSync(join(modules, name + '.ets'), 'utf8'), {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } }).outputText;
  vm.runInNewContext(code, { exports, require(specifier) {
    assert.ok(specifier.startsWith('./')); return load(specifier.slice(2));
  } }, { timeout: 1000 });
  return exports;
}
result.moduleActual = evaluate(vm.createContext({ exports: load('Application') }));
assert.deepEqual(result.moduleActual, result.expected);
result.negatives = [];
for (const [name, message] of [['Star', /invariant receiver/], ['MultipleBounds', /one noncyclic receiver bound/],
  ['Super', /super/i], ['Local', /local or inner classes/], ['Inner', /local or inner classes/]]) {
  const input = join(here, 'negatives', name + '.kt'), out = join(work, name + '.ets');
  run(name + '-jvm', 'bash', [compiler, input, '-d', join(work, name + '.jar')]);
  const diagnostic = JSON.parse(run(name, 'bash', [cli, '--mode', 'language', '--out', out, input], 2));
  assert.equal(diagnostic.code, 'UNSUPPORTED'); assert.match(diagnostic.message, message);
  assert.equal(diagnostic.source.file, input);
  assert.ok(diagnostic.source.start >= 0 && diagnostic.source.end > diagnostic.source.start);
  assert.equal(existsSync(out), false); result.negatives.push(diagnostic);
}
const proofJar = join(work, 'ir-proof.jar');
run('ir-build', 'bash', [compiler, ...['core/Frontend.kt', 'core/Constructors.kt', 'core/ConstructorDispatch.kt', 'core/DefaultArguments.kt', 'core/OfficialLowerings.kt',
  'core/ExpectedNullability.kt', 'core/LibraryInlining.kt', 'core/BinaryBodies.kt', 'core/LocalDeclarations.kt',
  'core/ForLoops.kt', 'core/Contract.kt', 'target/Tree.kt', 'target/Validator.kt', 'target/TypeSubstitution.kt',
  'target/Traversal.kt'].map(file => join(root, 'src', file)),
  join(here, 'IrEvidence.kt'), '-d', proofJar]);
result.irEvidence = run('ir-proof', 'java', ['-cp', `${proofJar}:${cp}`, 'dev.ets.IrEvidenceKt', cp, ...sources]).trim();
for (const input of inputs) assert.equal(hash(input.path), input.sha256, `Changed during verification: ${input.path}`);
result.passed = true; result.output = { path: output, sha256: hash(output) }; record();
console.log(`PASS ${result.actual.length} flat + ${result.moduleActual.length} multi-file JVM/ETS-host results; ${result.negatives.length} boundaries`);
console.log(result.irEvidence);
