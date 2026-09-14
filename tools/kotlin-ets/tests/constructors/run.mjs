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
function files(path) {
  return readdirSync(path, { withFileTypes: true }).flatMap(entry => entry.name === '.work' ? [] : entry.isDirectory()
    ? files(join(path, entry.name)) : [join(path, entry.name)]).sort();
}
const inputs = [...files(join(root, 'src')), ...files(here)].map(path => ({ path, sha256: hash(path) }));
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
const sources = ['Construction.kt', 'Application.kt', 'Roots.kt', 'SupportedNoPrimary.kt', 'Dispatch.kt'].map(name => join(here, name));
const compiler = join(root, 'tests/stdlib/compiler.sh'), cli = join(root, 'kotlin-ets');
const cp = run('classpath', 'bash', [compiler, '--classpath']).trim(), jar = join(work, 'oracle.jar');
run('jvm-build', 'bash', [compiler, ...sources, join(here, 'Oracle.kt'), '-d', jar]);
result.expected = run('jvm-run', 'java', ['-cp', `${jar}:${cp}`, 'constructorfixture.OracleKt']).trimEnd().split('\n');
const output = join(work, 'Construction.ets');
run('public-cli', 'bash', [cli, '--mode', 'language', '--out', output, ...sources]);
const code = readFileSync(output, 'utf8');
function check(paths) {
  const program = ts.createProgram(paths, { target: ts.ScriptTarget.ES2022,
    module: ts.ModuleKind.CommonJS, strict: true, noEmit: true, types: [] });
  assert.deepEqual(ts.getPreEmitDiagnostics(program).map(d => ts.flattenDiagnosticMessageText(d.messageText, '\n')), []);
}
const typecheck = join(work, 'Construction.ts'); writeFileSync(typecheck, code); check([typecheck]);
const tree = ts.createSourceFile(output, code, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
assert.deepEqual(tree.parseDiagnostics, []);
const chain = tree.statements.find(node => ts.isClassDeclaration(node) && node.name.text === 'Chain');
assert.equal(chain.members.filter(ts.isConstructorDeclaration).length, 1);
assert.deepEqual(chain.members.find(ts.isConstructorDeclaration).parameters.map(node => node.name.text), ['trace', 'number']);
const factories = chain.members.filter(node => ts.isMethodDeclaration(node) && node.modifiers?.some(m => m.kind === ts.SyntaxKind.StaticKeyword));
assert.equal(factories.length, 2);
assert.deepEqual(factories.map(node => node.parameters.map(p => p.name.text)), [['trace', 'label', 'count'], ['trace']]);
assert.ok(factories.every(node => node.name.text !== 'new_Chain'), 'Original method names must win');
const secret = tree.statements.find(node => ts.isClassDeclaration(node) && node.name.text === 'Secret');
const isPrivate = node => node.modifiers?.some(m => m.kind === ts.SyntaxKind.PrivateKeyword);
assert.ok(isPrivate(secret.members.find(ts.isConstructorDeclaration)));
assert.ok(isPrivate(secret.members.find(node => node.name?.text === 'adjusted')));
assert.equal(secret.members.filter(node => ts.isMethodDeclaration(node) && isPrivate(node) &&
  node.modifiers?.some(m => m.kind === ts.SyntaxKind.StaticKeyword)).length, 1);
const isStatic = node => node.modifiers?.some(m => m.kind === ts.SyntaxKind.StaticKeyword);
for (const [name, parameters, factoryCount] of [
  ['NativeRoot', ['seed'], 3], ['GenericNative', ['value'], 1], ['RootBase', ['trace', 'seed'], 0],
  ['RootChild', ['trace', 'seed'], 1], ['AbstractNative', ['value'], 0], ['Closed', ['value'], 1],
  ['NoPrimary', ['value'], 0],
]) {
  const declaration = tree.statements.find(node => ts.isClassDeclaration(node) && node.name.text === name);
  assert.equal(declaration.members.filter(ts.isConstructorDeclaration).length, 1);
  const constructor = declaration.members.find(ts.isConstructorDeclaration);
  assert.deepEqual(constructor.parameters.map(p => p.name.text), parameters);
  assert.equal(declaration.members.filter(node => ts.isMethodDeclaration(node) && isStatic(node)).length, factoryCount);
  if (name === 'Closed') assert.ok(isPrivate(constructor));
  if (name === 'GenericNative') {
    const factory = declaration.members.find(node => ts.isMethodDeclaration(node) && isStatic(node));
    assert.deepEqual(factory.typeParameters.map(p => p.name.text), ['T']);
    assert.equal(factory.type.getText(tree), 'GenericNative<T>');
  }
  if (name === 'RootChild') {
    const first = constructor.body.statements[0];
    assert.ok(ts.isExpressionStatement(first) && ts.isCallExpression(first.expression) &&
      first.expression.expression.kind === ts.SyntaxKind.SuperKeyword);
  }
}
assert.doesNotMatch(code, /Reflect\.|setPrototypeOf|newTarget/, 'No JS-specific allocation runtime');
for (const [name, privateEntry] of [['MultipleRoots', true], ['DispatchDefaults', true], ['EarlyDispatch', true],
  ['DispatchParent', false], ['AbstractDispatch', false], ['GenericDispatch', false]]) {
  const declaration = tree.statements.find(node => ts.isClassDeclaration(node) && node.name.text === name);
  const constructors = declaration.members.filter(ts.isConstructorDeclaration);
  assert.equal(constructors.length, 1);
  assert.equal(Boolean(isPrivate(constructors[0])), privateEntry);
  assert.equal(constructors[0].parameters[0].name.text, '__constructor');
}
const options = { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS };
const context = vm.createContext({ exports: {} });
vm.runInContext(ts.transpileModule(code, { compilerOptions: options }).outputText, context, { timeout: 1000 });
function evaluate(exports, Trace) {
  const scope = vm.createContext({ exports });
  return [0, -3, 7, -2147483648, 2147483647].flatMap(seed => {
    const values = ['construct', 'generic', 'inherited', 'captured', 'defaults', 'privateChain', 'reference',
      'nativeRoot', 'genericRoot', 'inheritedRoot', 'privateRoot', 'dispatchRoots', 'dispatchInheritance',
      'dispatchGeneric', 'dispatchDefaults', 'dispatchEarly'].map(name =>
      String(vm.runInContext(`exports.${name}(${seed})`, scope, { timeout: 1000 })));
    const trace = new Trace(); let outcome = 'ok';
    try { exports.failure(trace, seed); } catch (e) {
      assert.match(e.message, /zero/i); outcome = 'error';
    }
    return [...values, `${outcome}:${trace.value}`];
  });
}
result.actual = evaluate(context.exports, context.exports.Trace); record(); assert.deepEqual(result.actual, result.expected);
const modules = join(work, 'modules'), reversed = join(work, 'reversed');
run('modules', 'bash', [cli, '--mode', 'language', '--out-dir', modules, ...sources]);
run('reversed', 'bash', [cli, '--mode', 'language', '--out-dir', reversed, ...sources.toReversed()]);
assert.deepEqual(readdirSync(modules).sort(), ['Application.ets', 'Construction.ets', 'Dispatch.ets', 'Roots.ets', 'SupportedNoPrimary.ets']);
result.modules = readdirSync(modules).sort().map(name => ({ name, path: join(modules, name), sha256: hash(join(modules, name)) }));
for (const name of readdirSync(modules)) {
  assert.equal(readFileSync(join(modules, name), 'utf8'), readFileSync(join(reversed, name), 'utf8'));
  writeFileSync(join(modules, name.replace('.ets', '.ts')), readFileSync(join(modules, name), 'utf8'));
}
check(sources.map(path => join(modules, path.split('/').at(-1).replace('.kt', '.ts'))));
const cache = new Map();
function load(name) {
  if (cache.has(name)) return cache.get(name);
  const exports = {}; cache.set(name, exports);
  const code = ts.transpileModule(readFileSync(join(modules, name + '.ets'), 'utf8'), { compilerOptions: options }).outputText;
  vm.runInNewContext(code, { exports, require(specifier) {
    assert.ok(specifier.startsWith('./')); return load(specifier.slice(2));
  } }, { timeout: 1000 });
  return exports;
}
result.moduleActual = evaluate({ ...load('Application'), ...load('Dispatch') }, load('Construction').Trace); assert.deepEqual(result.moduleActual, result.expected);
result.regressions = [];
for (const name of ['MultipleRoots', 'SuperSecondary', 'Abstract']) {
  const input = join(here, 'negatives', name + '.kt'), out = join(work, name + '.ets');
  run(name + '-jvm', 'bash', [compiler, input, '-d', join(work, name + '.jar')]);
  run(name, 'bash', [cli, '--mode', 'language', '--out', out, input]);
  const path = out.replace('.ets', '.ts'); writeFileSync(path, readFileSync(out)); check([path]);
  result.regressions.push({ name, sha256: hash(out) });
}
result.negatives = [];
for (const [name, message] of [['Protected', /protected target member visibility/],
  ['Inner', /capture-aware allocation/], ['Local', /capture-aware allocation/],
  ['DispatchInheritedInitialization', /Using this during inherited initialization/],
  ['DispatchVirtualBody', /Using this during inherited initialization/],
  ['DispatchLocalInitializer', /local-class popup/]]) {
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
  'target/Traversal.kt'].map(file => join(root, 'src', file)), join(here, 'IrEvidence.kt'), '-d', proofJar]);
result.irEvidence = run('ir-proof', 'java', ['-cp', `${proofJar}:${cp}`, 'dev.ets.IrEvidenceKt', cp, ...sources]).trim();
for (const input of inputs) assert.equal(hash(input.path), input.sha256, `Changed during verification: ${input.path}`);
result.passed = true; result.output = { path: output, sha256: hash(output) }; record();
console.log(`PASS ${result.actual.length} flat + ${result.moduleActual.length} multi-file JVM/ETS-host results; ${result.negatives.length} boundaries`);
