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
const hash = path => createHash('sha256').update(readFileSync(path)).digest('hex');
function implementationHashes(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap(entry => {
    const path = join(directory, entry.name);
    return entry.isDirectory() ? implementationHashes(path) : [{ path, sha256: hash(path) }];
  });
}
const implementation = implementationHashes(join(root, 'src'));
const sourceInputs = [
  ...['Model.kt', 'Numbers.kt', 'Entry.kt', 'Oracle.kt'].map(name => join(here, name)),
  ...['Functions.kt', 'Classes.kt', 'LocalGeneric.kt', 'JvmOracle.kt'].map(name => join(root, 'tests/generics', name)),
].map(path => ({ path, sha256: hash(path) }));
mkdirSync(join(here, '.work'), { recursive: true });
const work = mkdtempSync(join(here, '.work/run-'));
console.log(`Evidence: ${work}`);
function run(label, command, args, expectedStatus = 0) {
  const result = spawnSync(command, args, { encoding: 'utf8', timeout: 180000 });
  writeFileSync(join(work, label + '.json'), JSON.stringify({ command, args, status: result.status,
    stdout: result.stdout, stderr: result.stderr }, null, 2));
  assert.equal(result.error, undefined);
  assert.equal(result.status, expectedStatus, result.stdout + result.stderr);
  return result.stdout;
}
const output = join(work, 'modules');
const sources = ['Numbers.kt', 'Entry.kt', 'Model.kt'].map(name => join(here, name));
const cli = join(root, 'kotlin-ets');
run('generate', 'bash', [cli, '--mode', 'language', '--out-dir', output, ...sources]);
assert.deepEqual(readdirSync(output).sort(), ['Entry.ets', 'Model.ets', 'Numbers.ets']);
const modules = new Map(readdirSync(output).map(name => [name, readFileSync(join(output, name), 'utf8')]));
function exportedNames(code) {
  const parsed = ts.createSourceFile('module.ets', code, ts.ScriptTarget.Latest, true);
  assert.deepEqual(parsed.parseDiagnostics, []);
  return parsed.statements.filter(node => node.modifiers?.some(modifier => modifier.kind === ts.SyntaxKind.ExportKeyword))
    .map(node => node.name?.text);
}
for (const name of ['Entry.ets', 'Numbers.ets']) {
  assert.equal(exportedNames(modules.get(name)).includes('localOffset'), false, 'Private source function must remain file-local');
}
assert.deepEqual(exportedNames(modules.get('Model.ets')), ['Counter', 'hiddenClassValue']);
assert.ok(exportedNames(modules.get('Numbers.ets')).includes('increment'), 'Internal functions must remain importable within the compilation');
const entry = ts.createSourceFile('Entry.ets', modules.get('Entry.ets'), ts.ScriptTarget.Latest, true);
assert.deepEqual(entry.parseDiagnostics, []);
const imports = entry.statements.filter(ts.isImportDeclaration);
assert.deepEqual(imports.flatMap(s => s.importClause.namedBindings.elements.map(n =>
  [s.moduleSpecifier.text, n.name.text, n.propertyName?.text])), [
  ['./Model', 'Counter', undefined], ['./Model', 'hiddenClassValue', undefined],
  ['./Numbers', 'access$hidden$tNumbersKt_0', undefined], ['./Numbers', 'access$hidden$tNumbersKt_1', undefined],
  ['./Numbers', 'access$identity$tNumbersKt', undefined], ['./Numbers', 'access$localOffset$tNumbersKt', undefined],
  ['./Numbers', 'access$withDefault$tNumbersKt', undefined],
  ['./Numbers', 'bump', undefined], ['./Numbers', 'label', undefined],
]);
const numbers = ts.createSourceFile('Numbers.ets', modules.get('Numbers.ets'), ts.ScriptTarget.Latest, true);
assert.deepEqual(numbers.statements.filter(ts.isImportDeclaration).flatMap(s =>
  s.importClause.namedBindings.elements.map(n => [s.moduleSpecifier.text, n.name.text])), [['./Model', 'Counter']]);
assert.deepEqual(numbers.statements.filter(ts.isFunctionDeclaration).map(s => s.name.text)
  .filter(name => name.startsWith('__ets')).sort(), ['__etsSubstring', '__etsSubstringFrom']);
assert.equal(entry.statements.filter(ts.isFunctionDeclaration).some(s => s.name.text.startsWith('__ets')), false);
function moduleLoader(modules) {
  const cache = new Map();
  function load(name) {
    if (cache.has(name)) return cache.get(name).exports;
    const module = { exports: {} };
    cache.set(name, module);
    assert.ok(modules.has(name), `Missing module: ${name}`);
    const result = ts.transpileModule(modules.get(name), { compilerOptions: {
      target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS }, reportDiagnostics: true });
    assert.deepEqual(result.diagnostics, []);
    vm.runInNewContext(result.outputText, { module, exports: module.exports, require(specifier) {
      assert.ok(specifier.startsWith('./'), `Unexpected external dependency: ${specifier}`);
      return load(specifier.slice(2) + '.ets');
    } }, { timeout: 1000 });
    return module.exports;
  }
  return load;
}
const load = moduleLoader(modules);
const compiler = join(root, 'tests/stdlib/compiler.sh');
run('jvm-compile', 'bash', [compiler, '-d', join(work, 'oracle.jar'), ...sources, join(here, 'Oracle.kt')]);
const cp = run('classpath', 'bash', [compiler, '--classpath']).trim();
const java = join(process.env.JAVA_HOME ?? '/Applications/Android Studio.app/Contents/jbr/Contents/Home', 'bin/java');
const expected = run('jvm', java, ['-cp', cp + ':' + join(work, 'oracle.jar'), 'modulefixture.OracleKt']).trim().split('\n');
const actual = [-2, 0, 41, 2147483647].map(value => load('Entry.ets').describe(value));
actual.push(...[-2, 0, 41, 2147483647].flatMap(value => [
  String(load('Entry.ets').entryLocalValue(value)), String(load('Numbers.ets').numbersLocalValue(value)),
]));
actual.push(...[-2, 0, 41, 2147483647].map(value => String(load('Entry.ets').privateClassValue(value))));
actual.push(...[-2, 0, 41, 2147483647].map(value => String(load('Entry.ets').crossFileInlineValue(value))));
actual.push(...[-2, 0, 41, 2147483647].map(value => load('Entry.ets').crossFileInlineGeneric(value)));
actual.push(...[-2, 0, 41, 2147483647].map(value => String(load('Entry.ets').crossFileInlineDefault(value))));
actual.push(...[-2, 0, 41, 2147483647].map(value => String(load('Entry.ets').crossFileInlineOverloaded(value))));
assert.equal(load('Numbers.ets').identity, undefined);
assert.deepEqual(exportedNames(modules.get('Numbers.ets')).filter(name => name.startsWith('access$')), [
  'access$localOffset$tNumbersKt', 'access$identity$tNumbersKt', 'access$withDefault$tNumbersKt',
  'access$hidden$tNumbersKt_0', 'access$hidden$tNumbersKt_1',
], 'One official accessor per private helper, including repeated generic calls');
assert.equal(load('Numbers.ets')['access$hidden$tNumbersKt'], undefined, 'Source declaration colliding with an accessor stays private');
assert.equal(load('Numbers.ets').hidden, undefined);
assert.equal(load('Model.ets').LocalCounter, undefined);
assert.equal(load('Entry.ets').localOffset, undefined);
assert.equal(load('Numbers.ets').localOffset, undefined);
for (const name of ['Entry.ets', 'Numbers.ets']) {
  assert.match(modules.get(name), /function localOffset\(/);
  assert.doesNotMatch(modules.get(name), /import \{ localOffset/);
}
assert.deepEqual(actual, expected);
writeFileSync(join(work, 'comparison.json'), JSON.stringify({ expected, actual }, null, 2));
const privateAccess = join(work, 'PrivateAccess.kt');
writeFileSync(privateAccess, 'package modulefixture\nfun leak(value: Int): Int = LocalCounter(value).value\n');
run('private-access-jvm', 'bash', [compiler, '-d', join(work, 'private-access.jar'), ...sources, privateAccess], 1);
const privateOutput = join(work, 'private-access');
const privateRejection = run('private-access-target', 'bash', [cli, '--mode', 'language', '--out-dir', privateOutput,
  ...sources, privateAccess], 1);
assert.equal(JSON.parse(privateRejection).code, 'COMPILATION_REJECTED');
assert.equal(existsSync(privateOutput), false, 'Illegal source access must not publish a target module');
const genericSources = ['Functions.kt', 'Classes.kt', 'LocalGeneric.kt'].map(name => join(root, 'tests/generics', name));
const genericOutput = join(work, 'generics');
run('generate-generics', 'bash', [cli, '--mode', 'language', '--out-dir', genericOutput, ...genericSources]);
assert.deepEqual(readdirSync(genericOutput).sort(), ['Classes.ets', 'Functions.ets', 'LocalGeneric.ets']);
const genericModules = new Map(readdirSync(genericOutput).map(name => [name, readFileSync(join(genericOutput, name), 'utf8')]));
const loadGeneric = moduleLoader(genericModules);
run('generic-jvm-compile', 'bash', [compiler, '-d', join(work, 'generic-oracle.jar'), ...genericSources,
  join(root, 'tests/generics/JvmOracle.kt')]);
const genericExpected = run('generic-jvm', java, ['-cp', cp + ':' + join(work, 'generic-oracle.jar'),
  'genericfixture.JvmOracleKt']).trim().split('\n');
const genericActual = [-7, 0, 3, 29].flatMap(seed => [loadGeneric('Functions.ets').functionCases(seed),
  loadGeneric('Classes.ets').classCases(seed), loadGeneric('LocalGeneric.ets').localCases(seed)]);
assert.deepEqual(genericActual, genericExpected);
writeFileSync(join(work, 'generic-comparison.json'), JSON.stringify({ expected: genericExpected, actual: genericActual }, null, 2));
run('no-overwrite', 'bash', [cli, '--mode', 'language', '--out-dir', output, ...sources], 1);
for (const [name, code] of modules) assert.equal(readFileSync(join(output, name), 'utf8'), code);
const conflicted = join(work, 'conflicted');
run('exclusive-output', 'bash', [cli, '--mode', 'language', '--out-dir', conflicted,
  '--out', join(work, 'also.ets'), ...sources], 1);
assert.equal(existsSync(conflicted), false);
assert.equal(existsSync(join(work, 'also.ets')), false);
const unsupported = join(work, 'Unsupported.kt');
writeFileSync(unsupported, 'package rejected\nfun wide(value: Long): Long = value + 1L\n');
const rejectedOutput = join(work, 'rejected');
run('no-partial-output', 'bash', [cli, '--mode', 'language', '--out-dir', rejectedOutput, ...sources, unsupported], 2);
assert.equal(existsSync(rejectedOutput), false);
mkdirSync(join(work, 'other'));
const colliding = join(work, 'other/Numbers.kt');
writeFileSync(colliding, 'package different\nfun alternate(): Int = 2\n');
const collisionOutput = join(work, 'collision');
const collision = JSON.parse(run('filename-collision', 'bash', [cli, '--mode', 'language', '--out-dir', collisionOutput, ...sources, colliding], 2));
assert.equal(collision.code, 'INVALID_TARGET');
assert.match(collision.message, /filenames collide/);
for (const path of [sources[0], colliding]) assert.ok(collision.message.includes(path));
assert.ok([sources[0], colliding].includes(collision.source.file));
assert.ok(collision.source.start >= 0 && collision.source.end > collision.source.start);
assert.equal(existsSync(collisionOutput), false);
assert.deepEqual(implementationHashes(join(root, 'src')), implementation, 'Compiler changed during verification');
for (const input of sourceInputs) assert.equal(hash(input.path), input.sha256, 'Kotlin source changed during verification');
writeFileSync(join(work, 'result.json'), JSON.stringify({ passed: true, output, genericOutput, implementation, sourceInputs,
  checks: ['JVM differential', 'per-file same-name methods', 'source private/internal visibility', 'illegal private access rejection',
    'function and type imports', 'helper dependency closure',
    'no overwrite', 'exclusive output options', 'no partial output', 'filename collision'] }, null, 2));
console.log(`PASS ${actual.length + genericActual.length} JVM/module cases; generic class/function cycles, explicit imports, source filenames, no overwrite`);
