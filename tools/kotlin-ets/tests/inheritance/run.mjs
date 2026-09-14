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
function sources(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap(entry => entry.isDirectory()
    ? sources(join(directory, entry.name)) : [join(directory, entry.name)]).sort();
}
const inputs = [...sources(join(root, 'src')), ...readdirSync(here).filter(name => name.endsWith('.kt')).map(name => join(here, name))]
  .map(path => ({ path, sha256: hash(path) }));
const env = { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' };
const result = { inputs, commands: [], JAVA_TOOL_OPTIONS: env.JAVA_TOOL_OPTIONS };
const record = () => writeFileSync(join(work, 'result.json'), JSON.stringify(result, null, 2));
function run(label, command, args, status = 0) {
  const value = spawnSync(command, args, { env, encoding: 'utf8', timeout: 600000, maxBuffer: 16 * 1024 * 1024 });
  writeFileSync(join(work, label + '.stdout'), value.stdout ?? '');
  writeFileSync(join(work, label + '.stderr'), value.stderr ?? '');
  result.commands.push({ label, command, args, status: value.status }); record();
  assert.equal(value.error, undefined);
  assert.equal(value.status, status, value.stdout + value.stderr);
  return value.stdout;
}
const compiler = join(root, 'tests/stdlib/compiler.sh'), source = join(here, 'Inheritance.kt');
const cp = run('classpath', 'bash', [compiler, '--classpath']).trim(), jar = join(work, 'oracle.jar');
run('jvm-build', 'bash', [compiler, source, join(here, 'JvmOracle.kt'), '-d', jar]);
result.expected = run('jvm-run', 'java', ['-cp', `${jar}:${cp}`, 'inheritancefixture.JvmOracleKt']).trimEnd().split('\n');
const output = join(work, 'Inheritance.ets');
run('public-cli', 'bash', [join(root, 'kotlin-ets'), '--mode', 'language', '--out', output, source]);
const code = readFileSync(output, 'utf8');
const typecheckPath = join(work, 'Inheritance.ts');
writeFileSync(typecheckPath, code);
const checked = ts.createProgram([typecheckPath], { target: ts.ScriptTarget.ES2022,
  module: ts.ModuleKind.CommonJS, strict: true, noEmit: true, types: [] });
assert.deepEqual(ts.getPreEmitDiagnostics(checked).map(d => ts.flattenDiagnosticMessageText(d.messageText, '\n')), []);
const tree = ts.createSourceFile(output, code, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
assert.deepEqual(tree.parseDiagnostics, []);
for (const [name, methodName, parameters] of [['Operation', 'apply', ['left', 'right']], ['Derived', 'apply', ['left', 'right']],
  ['Base', 'inherited', ['delta']], ['AbstractOperation', 'twice', ['value']]]) {
  const declaration = tree.statements.find(node => (ts.isClassDeclaration(node) || ts.isInterfaceDeclaration(node)) && node.name.text === name);
  assert.ok(declaration, name);
  const method = declaration.members.find(node => node.name?.text === methodName);
  assert.deepEqual(method.parameters.map(parameter => parameter.name.text), parameters);
  if (ts.isInterfaceDeclaration(declaration)) assert.equal(method.body, undefined);
}
const compiled = ts.transpileModule(code, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS }, reportDiagnostics: true });
assert.deepEqual(compiled.diagnostics, []);
const context = vm.createContext({ exports: {} });
vm.runInContext(compiled.outputText, context, { timeout: 1000 });
result.actual = [];
for (const seed of [0, -3, 7, -2147483648, 2147483647]) {
  for (const invocation of [`dispatch(${seed})`, `abstractDispatch(${seed})`, `callEffects(${seed})`,
    `constructorEffects(${seed})`, `selected(true,${seed})`, `selected(false,${seed})`, `propertyDispatch(${seed})`, `propertyInterface(${seed})`]) {
    result.actual.push(String(vm.runInContext('exports.' + invocation, context, { timeout: 1000 })));
  }
}
record(); assert.deepEqual(result.actual, result.expected);
assert.match(code, /get computed\(\)/);
assert.match(code, /set computed\(next: T\)/);
assert.match(code, /interface PropertyView<T>\s*\{\s*readonly value: T;/);
const interfaceOutput = join(work, 'SupportedInterfaceProperty.ets');
run('supported-interface-property', 'bash', [join(root, 'kotlin-ets'), '--mode', 'language',
  '--out', interfaceOutput, join(here, 'SupportedInterfaceProperty.kt')]);
assert.match(readFileSync(interfaceOutput, 'utf8'), /readonly value: number;/);
const inheritedOutput = join(work, 'SupportedInheritedProperty.ets');
run('supported-inherited-property', 'bash', [join(root, 'kotlin-ets'), '--mode', 'language',
  '--out', inheritedOutput, join(here, 'SupportedInheritedProperty.kt')]);
const inheritedJs = ts.transpileModule(readFileSync(inheritedOutput, 'utf8'), { compilerOptions: {
  target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } });
assert.equal(vm.runInNewContext(inheritedJs.outputText + '\ninheritedProperty(new PropertyChild())',
  { exports: {} }, { timeout: 1000 }), 3);
const supportedGeneric = join(work, 'SupportedGeneric.ets');
run('supported-generic', 'bash', [join(root, 'kotlin-ets'), '--mode', 'language', '--out', supportedGeneric, join(here, 'SupportedGeneric.kt')]);
const supportedCode = readFileSync(supportedGeneric, 'utf8');
assert.ok(supportedCode.includes('class GenericChild extends GenericBase<number>'));
const supportedJs = ts.transpileModule(supportedCode, { compilerOptions: {
  target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS }, reportDiagnostics: true });
assert.deepEqual(supportedJs.diagnostics, []);
assert.equal(vm.runInNewContext(supportedJs.outputText + '\nnew GenericChild().value', { exports: {} }, { timeout: 1000 }), 3);
result.supportedGeneric = { path: supportedGeneric, sha256: hash(supportedGeneric) };
// Retain this historical filename as a legacy positive with mandatory interface-only JVM/public proof.
// This is an explicit positive contract check, not a runtime-body claim or an unchecked negative skip.
const genericMethodInput = join(here, 'UnsupportedGenericMethod.kt');
run('generic-method-interface-proof', process.execPath,
  [join(here, 'methods/interface-proof.mjs'), genericMethodInput]);
result.supportedGenericMethod = { input: genericMethodInput, sha256: hash(genericMethodInput),
  proofLog: join(work, 'generic-method-interface-proof.stdout') };
const negatives = readdirSync(here).filter(name => name.startsWith('Unsupported') && name.endsWith('.kt') &&
  join(here, name) !== genericMethodInput).sort();
for (const name of negatives) {
  const input = join(here, name), out = join(work, name + '.ets');
  const diagnostic = JSON.parse(run(name, 'bash', [join(root, 'kotlin-ets'), '--mode', 'language', '--out', out, input], 2));
  assert.equal(diagnostic.code, 'UNSUPPORTED');
  assert.equal(diagnostic.source.file, input);
  assert.ok(diagnostic.source.start >= 0 && diagnostic.source.end > diagnostic.source.start);
  assert.equal(existsSync(out), false);
}
for (const input of inputs) assert.equal(hash(input.path), input.sha256, `Changed during verification: ${input.path}`);
result.output = { path: output, sha256: hash(output) }; result.passed = true; record();
console.log(`PASS ${result.actual.length} same-input JVM/host inheritance cases; ${negatives.length} source-linked unsupported boundaries; declaration names preserved`);
