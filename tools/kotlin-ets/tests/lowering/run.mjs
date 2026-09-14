import assert from 'node:assert/strict';
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
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
function run(label, command, args) {
  const result = spawnSync(command, args, { encoding: 'utf8' });
  writeFileSync(join(work, `${label}.json`), JSON.stringify({ command, args, status: result.status,
    stdout: result.stdout, stderr: result.stderr }, null, 2));
  if (result.error) throw result.error;
  assert.equal(result.status, 0, `${label}: ${result.stdout}\n${result.stderr}`);
  return result.stdout;
}
const compiler = join(root, 'tests/stdlib/compiler.sh');
const classpath = run('classpath', 'bash', [compiler, '--classpath']).trim();
const fixture = join(here, 'Concatenation.kt');
const jvmJar = join(work, 'oracle.jar');
run('jvm-compile', 'bash', [compiler, fixture, join(here, 'JvmOracle.kt'), '-d', jvmJar]);
const expected = run('jvm-runtime', 'java', ['-cp', `${jvmJar}:${classpath}`, 'loweringfixture.JvmOracleKt']).trim().split('\n');
assert.deepEqual(expected, ['nullA8|B9:AB', 'nullA-1|B0:AB', 'start:X11/Y12:XY', 'decimal=1.0:null',
  'item=seen2|changed13|seen13;count=14;events=T2>M3>T13>',
  'item=seen-3|changed8|seen8;count=9;events=T-3>M-2>T8>']);

const output = join(work, 'concatenation.ets');
run('public-cli', 'bash', [join(root, 'kotlin-ets'), '--mode', 'language', '--out', output, fixture]);
const source = readFileSync(output, 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS }, reportDiagnostics: true,
});
assert.deepEqual(compiled.diagnostics, []);
const context = { exports: {} };
vm.runInNewContext(compiled.outputText, context, { timeout: 1000 });
const actual = [context.exports.orderedConcatenation(7), context.exports.orderedConcatenation(-2),
  context.exports.renamedConcatenation(10), context.exports.foldedConstants(),
  context.exports.stringifyBeforeMutation(2), context.exports.stringifyBeforeMutation(-3)];
writeFileSync(join(work, 'runtime.json'), JSON.stringify({ expected, actual }, null, 2));
assert.deepEqual(actual, expected);
assert.match(source, /orderedConcatenation\(initialValue: number\)/);
assert.match(source, /renamedConcatenation\(startingValue: number\)/);
console.log('PASS public CLI / same-input JVM: nullable concatenation, constant formatting, ordered effects and preserved names');
console.log('PASS side-effectful toString: conversion before mutation, conversion after mutation, exact counts and event order');

const evidenceJar = join(work, 'ir-evidence.jar');
run('ir-compile', 'bash', [compiler, ...['core/Frontend.kt', 'core/Constructors.kt', 'core/ConstructorDispatch.kt', 'core/DefaultArguments.kt', 'core/OfficialLowerings.kt', 'core/ExpectedNullability.kt', 'core/LibraryInlining.kt', 'core/BinaryBodies.kt', 'core/LocalDeclarations.kt', 'core/ForLoops.kt',
  'core/Contract.kt', 'core/CallCaptures.kt', 'core/GenericBounds.kt', 'target/Tree.kt', 'target/Validator.kt', 'target/TypeSubstitution.kt', 'target/Traversal.kt'].map(file => join(root, 'src', file)),
  join(here, 'IrEvidence.kt'), '-d', evidenceJar]);
console.log(run('ir-evidence', 'java', ['-cp', `${evidenceJar}:${classpath}`, 'dev.ets.IrEvidenceKt', fixture, classpath, work]).trim());
