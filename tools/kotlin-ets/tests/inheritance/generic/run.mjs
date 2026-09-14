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
const implementations = readdirSync(join(root, 'src'), { recursive: true }).filter(path => path.endsWith('.kt')).map(path => join(root, 'src', path)).sort();
const fixtures = readdirSync(here).filter(name => name.endsWith('.kt')).map(name => join(here, name));
const result = { inputs: [...implementations, ...fixtures, fileURLToPath(import.meta.url)].map(path => ({ path, sha256: hash(path) })), commands: [] };
const record = () => writeFileSync(join(work, 'result.json'), JSON.stringify(result, null, 2));
const cwd = process.cwd(), env = { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' };
function run(label, command, args, expectedStatus = 0) {
  const value = spawnSync(command, args, { cwd, env, encoding: 'utf8', timeout: 600000, maxBuffer: 16 * 1024 * 1024 });
  writeFileSync(join(work, label + '.stdout'), value.stdout ?? '');
  writeFileSync(join(work, label + '.stderr'), value.stderr ?? '');
  result.commands.push({ label, command, args, cwd, status: value.status }); record();
  assert.equal(value.error, undefined);
  assert.equal(value.status, expectedStatus, value.stdout + value.stderr);
  return value;
}
const compiler = join(root, 'tests/stdlib/compiler.sh'), source = join(here, 'GenericHeritage.kt');
const cp = run('classpath', 'bash', [compiler, '--classpath']).stdout.trim(), jar = join(work, 'oracle.jar');
run('jvm-build', 'bash', [compiler, source, join(here, 'JvmOracle.kt'), '-d', jar]);
result.expected = run('jvm-run', 'java', ['-cp', `${jar}:${cp}`, 'genericheritage.JvmOracleKt']).stdout.trimEnd().split('\n');
const output = join(work, 'GenericHeritage.ets');
run('public-cli', 'bash', [join(root, 'kotlin-ets'), '--mode', 'language', '--out', output, source]);
const code = readFileSync(output, 'utf8');
const tree = ts.createSourceFile(output, code, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
assert.deepEqual(tree.parseDiagnostics, []);
for (const [name, parameter] of [['Value', 'T'], ['Storage', 'T'], ['Forward', 'U'], ['Nested', 'V'], ['Both', 'T']]) {
  const declaration = tree.statements.find(node => (ts.isClassDeclaration(node) || ts.isInterfaceDeclaration(node)) && node.name.text === name);
  assert.ok(declaration, name);
  assert.deepEqual(declaration.typeParameters.map(p => p.name.text), [parameter]);
}
const compiled = ts.transpileModule(code, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS }, reportDiagnostics: true });
assert.deepEqual(compiled.diagnostics, []);
const context = vm.createContext({ exports: {} });
vm.runInContext(compiled.outputText, context, { timeout: 1000 });
result.actual = [];
for (const seed of [0, -3, 7, -2147483648, 2147483647]) {
  for (const name of ['genericDispatch', 'parameterized', 'nestedArguments', 'stringDispatch', 'constructorEffects', 'genericCaller']) {
    result.actual.push(String(vm.runInContext(`exports.${name}(${seed})`, context, { timeout: 1000 })));
  }
}
result.actual.push(String(vm.runInContext('exports.migratedGeneric()', context, { timeout: 1000 })));
record(); assert.equal(result.expected.length, 31); assert.deepEqual(result.actual, result.expected);
// Preserve the exact former negative as an explicit public positive after R2C public-QGPUk6.
const supported = join(here, 'SupportedMemberGeneric.kt'), supportedOut = join(work, 'SupportedMemberGeneric.ets');
run('supported-generic-member', 'bash', [join(root, 'kotlin-ets'), '--mode', 'language', '--out', supportedOut, supported]);
assert.ok(existsSync(supportedOut));
const propertyOut = join(work, 'SupportedInheritedProperty.ets');
run('supported-inherited-property', 'bash', [join(root, 'kotlin-ets'), '--mode', 'language',
  '--out', propertyOut, join(here, 'SupportedInheritedProperty.kt')]);
const propertyJs = ts.transpileModule(readFileSync(propertyOut, 'utf8'), { compilerOptions: {
  target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } });
assert.equal(vm.runInNewContext(propertyJs.outputText + '\ninheritedProperty(new PropertyChild())',
  { exports: {} }, { timeout: 1000 }), 1);
for (const input of fixtures.filter(path => path.includes('/Unsupported'))) {
  const name = input.slice(input.lastIndexOf('/') + 1), out = join(work, name + '.ets');
  if (name === 'UnsupportedVariance.kt') {
    run(name, 'bash', [join(root, 'kotlin-ets'), '--mode', 'language', '--out', out, input]);
    const js = ts.transpileModule(readFileSync(out, 'utf8'), { compilerOptions: {
      target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } }).outputText;
    assert.equal(vm.runInNewContext(js + '\nnew VariantText().read()', { exports: {} }, { timeout: 1000 }), 'text');
    continue;
  }
  const diagnostic = JSON.parse(run(name, 'bash', [join(root, 'kotlin-ets'), '--mode', 'language', '--out', out, input], 2).stdout);
  assert.equal(diagnostic.code, 'UNSUPPORTED');
  assert.equal(diagnostic.source.file, input);
  assert.ok(diagnostic.source.start >= 0 && diagnostic.source.end > diagnostic.source.start);
  assert.equal(existsSync(out), false);
}
const invalid = join(here, 'InvalidDiamond.kt'), rejectedJar = join(work, 'invalid.jar'), rejectedEts = join(work, 'invalid.ets');
function identifiesInput(stderr) {
  return [...stderr.matchAll(/^(.+\.kt):\d+:\d+: error:/gm)].some(match => resolve(cwd, match[1]) === invalid);
}
const jvm = run('diamond-jvm', 'bash', [compiler, invalid, '-d', rejectedJar], 1);
assert.ok(identifiesInput(jvm.stderr)); assert.equal(existsSync(rejectedJar), false);
const cli = run('diamond-cli', 'bash', [join(root, 'kotlin-ets'), '--mode', 'language', '--out', rejectedEts, invalid], 1);
assert.equal(JSON.parse(cli.stdout).code, 'COMPILATION_REJECTED');
assert.ok(identifiesInput(cli.stderr)); assert.equal(existsSync(rejectedEts), false);
for (const input of result.inputs) assert.equal(hash(input.path), input.sha256, `Changed during verification: ${input.path}`);
result.output = { path: output, sha256: hash(output) }; result.passed = true; record();
console.log('PASS 31 same-input JVM/public-CLI host results, generic-member, inherited-property and unchanged variance positives, one source-linked boundary and incompatible-diamond JVM/frontend rejection');
