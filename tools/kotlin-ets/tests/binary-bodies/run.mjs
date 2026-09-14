import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync, rmSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../..');
process.env.JAVA_TOOL_OPTIONS = '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC';
process.env.PATH = `${process.env.JAVA_HOME ?? '/Applications/Android Studio.app/Contents/jbr/Contents/Home'}/bin:${process.env.PATH}`;
mkdirSync(join(here, '.work'), { recursive: true });
const work = mkdtempSync(join(here, '.work/policy-'));
console.log(`Evidence: ${work}`);
function run(label, command, args, expected = 0) {
  const result = spawnSync(command, args, { encoding: 'utf8', timeout: 300000 });
  writeFileSync(join(work, `${label}.json`), JSON.stringify({ command, args, status: result.status,
    stdout: result.stdout, stderr: result.stderr, error: result.error?.message }, null, 2));
  if (result.error) throw result.error;
  assert.equal(result.status, expected, `${label}: ${result.stdout}\n${result.stderr}`);
  return result.stdout;
}
const compiler = join(root, 'tests/stdlib/compiler.sh');
const cp = run('classpath', 'bash', [compiler, '--classpath']).trim();
const producer = join(work, 'producer');
mkdirSync(producer);
const library = join(producer, 'BinaryLibrary.kt');
writeFileSync(library, readFileSync(join(here, 'BinaryLibrary.kt')));
const application = join(here, 'Application.kt');
const provenance = [];
for (const kind of ['signature', 'serialized']) {
  const jar = join(work, `${kind}.jar`);
  run(`${kind}-build`, 'bash', [compiler, ...(kind === 'serialized' ? ['-Xserialize-ir=inline'] : []), library, '-d', jar]);
  provenance.push({ kind, jar, sha256: createHash('sha256').update(readFileSync(jar)).digest('hex') });
}
writeFileSync(join(work, 'provenance.json'), JSON.stringify(provenance, null, 2));
rmSync(producer, { recursive: true });
assert.equal(existsSync(library), false);
const oracle = join(work, 'oracle.jar');
const serialized = provenance[1].jar;
const evidence = join(work, 'evidence.jar');
run('evidence-build', 'bash', [compiler, ...['Frontend.kt', 'DefaultArguments.kt', 'LibraryInlining.kt', 'BinaryBodies.kt', 'OfficialLowerings.kt',
  'LocalDeclarations.kt', 'ForLoops.kt', 'ExpectedNullability.kt', 'Contract.kt'].map(name => join(root, 'src/core', name)),
  ...['Tree.kt', 'TypeSubstitution.kt', 'Validator.kt', 'Traversal.kt'].map(name => join(root, 'src/target', name)),
  join(here, 'BodyEvidence.kt'), '-d', evidence]);
console.log(run('body-evidence', 'java', ['-cp', `${cp}:${evidence}`, 'dev.ets.BodyEvidenceKt', `${cp}:${serialized}`, application, work]).trim());
console.log(run('signature-body-evidence', 'java', ['-cp', `${cp}:${evidence}`, 'dev.ets.BodyEvidenceKt',
  `${cp}:${provenance[0].jar}`, application, work, 'signature-only']).trim());
const strip = join(work, 'strip.jar');
run('strip-build', 'bash', [compiler, join(here, 'StripSource.kt'), '-d', strip]);
const noSource = join(work, 'no-source.jar');
run('strip-source', 'java', ['-cp', `${cp}:${strip}`, 'binarytest.StripSourceKt', serialized, noSource]);
const unresolved = join(work, 'unresolved.jar');
run('unresolved-build', 'bash', [compiler, '-Xserialize-ir=inline', join(here, 'MissingDependency.kt'), '-d', unresolved]);
for (const [label, jar, message] of [['no-source', noSource, 'no SourceFile attribute'],
  ['unresolved', unresolved, 'unsupported serialized body call:']]) {
  console.log(run(`${label}-evidence`, 'java', ['-cp', `${cp}:${evidence}`, 'dev.ets.BodyEvidenceKt',
    `${cp}:${jar}`, application, work, message, label]).trim());
}
if (process.argv.includes('--evidence-only')) {
  console.log('PASS frontend contract only; public CLI/runtime not executed in this mode');
  process.exit(0);
}
function reject(label, jar, message) {
  const output = join(work, `${label}.ets`);
  const diagnostic = JSON.parse(run(`${label}-cli`, 'bash', [join(root, 'kotlin-ets'), '--mode', 'language',
    '--classpath', `${cp}:${jar}`, '--out', output, application], 2));
  assert.equal(diagnostic.code, 'UNSUPPORTED');
  assert.match(diagnostic.message, /binarylibrary.*binaryTransform/);
  assert.match(diagnostic.message, message);
  assert.equal(diagnostic.source.file, application);
  assert.ok(diagnostic.source.start >= 0 && diagnostic.source.end > diagnostic.source.start);
  assert.equal(existsSync(output), false);
}
reject('signature', provenance[0].jar, /JVM binary metadata contains no serialized IR/);
reject('no-source', noSource, /no SourceFile attribute; source identity unavailable/);
reject('unresolved', unresolved, /unsupported serialized body call:.*hiddenOffset/);
run('oracle-build', 'bash', [compiler, '-classpath', `${cp}:${serialized}`, application, join(here, 'JvmOracle.kt'), '-d', oracle]);
const expected = run('oracle-run', 'java', ['-cp', `${cp}:${serialized}:${oracle}`, 'binaryapplication.JvmOracleKt']).trim().split('\n');
assert.deepEqual(expected, ['45:16:7:4:BALD', '129:23:14:11:BALD']);
const target = join(work, 'binary-backed.ets');
run('binary-cli', 'bash', [join(root, 'kotlin-ets'), '--mode', 'language', '--classpath', `${cp}:${serialized}`, '--out', target, application]);
const compiled = ts.transpileModule(readFileSync(target, 'utf8'), {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS }, reportDiagnostics: true,
});
assert.deepEqual(compiled.diagnostics, []);
const context = { exports: {} };
vm.runInNewContext(compiled.outputText, context, { timeout: 1000 });
const actual = [1, 8].map(seed => context.exports.binaryScenario(seed));
writeFileSync(join(work, 'runtime.json'), JSON.stringify({ route: 'serialized-jar-only', expected, actual }, null, 2));
assert.deepEqual(actual, expected);
console.log('PASS signature-only rejection and serialized-JAR-only CLI/JVM differential');
