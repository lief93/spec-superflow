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
const source = join(here, 'LocalFunctions.kt');
const manifest = { implementation: identities(join(root, 'src')),
  sourceInputs: [source, join(here, 'JvmOracle.kt')].map(path => ({ path, sha256: hash(path) })), commands: [] };
const record = () => writeFileSync(join(work, 'result.json'), JSON.stringify(manifest, null, 2));
function run(label, command, args, expectedStatus = 0) {
  const result = spawnSync(command, args, { encoding: 'utf8', timeout: 600000, maxBuffer: 16 * 1024 * 1024 });
  const stdout = join(work, label + '.stdout');
  const stderr = join(work, label + '.stderr');
  writeFileSync(stdout, result.stdout ?? '');
  writeFileSync(stderr, result.stderr ?? '');
  manifest.commands.push({ label, command, args, status: result.status, error: result.error?.message, stdout, stderr });
  record();
  assert.equal(result.error, undefined);
  assert.equal(result.status, expectedStatus, `${label}: ${result.stdout}\n${result.stderr}`);
  return result.stdout;
}
record();
const compiler = join(root, 'tests/stdlib/compiler.sh');
const cp = run('classpath', 'bash', [compiler, '--classpath']).trim();
const oracle = join(work, 'oracle.jar');
run('jvm-build', 'bash', [compiler, source, join(here, 'JvmOracle.kt'), '-d', oracle]);
manifest.expected = run('jvm-run', 'java', ['-cp', `${oracle}:${cp}`, 'localfixture.JvmOracleKt']).trim().split('\n');
assert.equal(manifest.expected.length, 4);
assert.equal(manifest.expected[1], '0:item:10|2:5:9:10:10|1:2:11:3|1:1:RLAD|5|3|new:1');
const evidence = join(work, 'evidence.jar');
run('evidence-build', 'bash', [compiler, ...[
  'core/Frontend.kt', 'core/OfficialLowerings.kt', 'core/ExpectedNullability.kt', 'core/LibraryInlining.kt', 'core/BinaryBodies.kt', 'core/LocalDeclarations.kt', 'core/ForLoops.kt',
  'core/Contract.kt', 'target/Tree.kt', 'target/Validator.kt', 'target/TypeSubstitution.kt', 'target/Traversal.kt',
].map(path => join(root, 'src', path)), join(here, 'LocalEvidence.kt'), '-d', evidence]);
console.log(run('official-evidence', 'java', ['-cp', `${evidence}:${cp}`, 'dev.ets.LocalEvidenceKt', source, cp, work]).trim());
manifest.output = join(work, 'LocalFunctions.ets');
run('public-cli', 'bash', [join(root, 'kotlin-ets'), '--mode', 'language', '--out', manifest.output, source]);
const code = readFileSync(manifest.output, 'utf8');
const syntax = ts.createSourceFile('LocalFunctions.ts', code, ts.ScriptTarget.Latest, true);
assert.deepEqual(syntax.parseDiagnostics, []);
function checkSyntax(node) {
  if (ts.isFunctionDeclaration(node)) {
    assert.ok(ts.isSourceFile(node.parent), 'Local functions must be lifted before printing');
  }
  if (ts.isArrowFunction(node)) assert.equal(node.typeParameters?.length ?? 0, 0, 'ETS rejects generic arrows');
  ts.forEachChild(node, checkSyntax);
}
checkSyntax(syntax);
for (const [name, parameters] of [
  ['localIdentity', ['value']], ['localGenericCapture', ['value', 'depth']],
  ['localGenericMutation', ['value', 'replacement']],
  ['localRecursion', ['seed']], ['sharedCapture', ['seed']],
  ['escapingCapture', ['seed']], ['localOrder', ['seed']],
  ['nestedCapture', ['seed']], ['localsScenario', ['seed']],
]) {
  const declaration = syntax.statements.find(node => ts.isFunctionDeclaration(node) && node.name.text === name);
  assert.ok(declaration, `Original method disappeared: ${name}`);
  assert.deepEqual(declaration.parameters.map(parameter => parameter.name.text), parameters);
}
const compiled = ts.transpileModule(code, { compilerOptions: {
  target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS,
}, reportDiagnostics: true });
assert.deepEqual(compiled.diagnostics, []);
const context = { exports: {} };
vm.runInNewContext(compiled.outputText, context, { timeout: 1000 });
manifest.actual = [-2, 0, 5, 2147483647].map(seed => String(context.exports.localsScenario(seed)));
assert.deepEqual(manifest.actual, manifest.expected);
for (const [name, message] of [['ReservedCell', /reserved|__ets/i], ['UninitializedCapture', /initializer/i]]) {
  const rejectedOutput = join(work, name + '.ets');
  const rejectedSource = join(here, name + '.kt');
  manifest.sourceInputs.push({ path: rejectedSource, sha256: hash(rejectedSource) });
  const diagnostic = JSON.parse(run(name, 'bash', [join(root, 'kotlin-ets'), '--mode', 'language',
    '--out', rejectedOutput, rejectedSource], 2));
  assert.equal(diagnostic.code, 'UNSUPPORTED');
  assert.match(diagnostic.message, message);
  assert.equal(diagnostic.source.file, rejectedSource);
  assert.ok(diagnostic.source.start >= 0 && diagnostic.source.end > diagnostic.source.start);
  assert.equal(existsSync(rejectedOutput), false);
}
manifest.outputSha256 = hash(manifest.output);
for (const input of [...manifest.implementation, ...manifest.sourceInputs]) {
  assert.equal(hash(input.path), input.sha256, `Changed during verification: ${input.path}`);
}
manifest.passed = true;
record();
console.log('PASS JVM/host target: generic locals, recursive capture, shared mutable capture, escaping closures, argument order and nested locals');
