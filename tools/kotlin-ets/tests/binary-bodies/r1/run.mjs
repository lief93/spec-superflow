import assert from 'node:assert/strict';
import { mkdirSync, mkdtempSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../../..');
process.env.JAVA_TOOL_OPTIONS = '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC';
process.env.PATH = `/Applications/Android Studio.app/Contents/jbr/Contents/Home/bin:${process.env.PATH}`;
mkdirSync(join(here, '../.work'), { recursive: true });
const work = mkdtempSync(join(here, '../.work/r1-'));
console.log(`Evidence: ${work}`);
function run(label, command, args, status = 0) {
  const result = spawnSync(command, args, { encoding: 'utf8', timeout: 300000 });
  writeFileSync(join(work, `${label}.json`), JSON.stringify({ command, args, status: result.status,
    stdout: result.stdout, stderr: result.stderr, error: result.error?.message }, null, 2));
  if (result.error) throw result.error;
  assert.equal(result.status, status, `${label}: ${result.stdout}\n${result.stderr}`);
  return result.stdout;
}
const compiler = join(root, 'tests/stdlib/compiler.sh');
const cp = run('classpath', 'bash', [compiler, '--classpath']).trim();
const library = join(work, 'same.jar');
run('producer', 'bash', [compiler, '-Xserialize-ir=inline', join(here, 'Same.kt'), '-d', library]);
const oracle = join(work, 'oracle.jar');
run('oracle-build', 'bash', [compiler, '-classpath', `${cp}:${library}`, join(here, 'Application.kt'), join(here, 'Oracle.kt'), '-d', oracle]);
assert.deepEqual(run('jvm', 'java', ['-cp', `${cp}:${library}:${oracle}`, 'consumer.OracleKt']).trim().split('\n'),
  ['27/2/:1:2', '-15/2/:-2:-1', '-1/2/:2147483647:-2147483648']);
const evidence = join(work, 'evidence.jar');
run('evidence-build', 'bash', [compiler, ...['Frontend.kt', 'LibraryInlining.kt', 'BinaryBodies.kt', 'OfficialLowerings.kt',
  'LocalDeclarations.kt', 'ForLoops.kt', 'ExpectedNullability.kt', 'Contract.kt'].map(name => join(root, 'src/core', name)),
  ...['Tree.kt', 'TypeSubstitution.kt', 'Validator.kt', 'Traversal.kt'].map(name => join(root, 'src/target', name)),
  join(here, 'Evidence.kt'), '-d', evidence]);
function inspect(label, jars, mode = '2') {
  const dir = join(work, label);
  mkdirSync(dir);
  console.log(run(label, 'java', ['-cp', `${cp}:${evidence}`, 'dev.ets.r1.EvidenceKt', `${cp}:${jars.join(':')}`,
    join(here, 'Application.kt'), dir, mode]).trim());
}
inspect('same-evidence', [library], '1');
const helper = join(work, 'helper.jar');
run('helper-build', 'bash', [compiler, '-Xserialize-ir=inline', join(here, 'Helper.kt'), '-d', helper]);
const entry = join(work, 'entry.jar');
run('entry-build', 'bash', [compiler, '-classpath', `${cp}:${helper}`, '-Xserialize-ir=inline', join(here, 'Entry.kt'), '-d', entry]);
inspect('second-jar', [entry, helper]);
const combined = join(work, 'combined.jar');
run('combined-build', 'bash', [compiler, '-Xserialize-ir=inline', join(here, 'Entry.kt'), join(here, 'Helper.kt'), '-d', combined]);
inspect('cross-facade', [combined]);
const plain = join(work, 'signature-helper.jar');
run('plain-helper-build', 'bash', [compiler, join(here, 'Helper.kt'), '-d', plain]);
inspect('missing-body', [entry, plain], 'reject:missing serialized IR body for dependency');
inspect('missing-jar', [entry], 'reject:unlinked serialized dependencies:');
const strip = join(work, 'strip.jar');
run('strip-build', 'bash', [compiler, join(here, '../StripSource.kt'), '-d', strip]);
const noSource = join(work, 'no-source-helper.jar');
run('strip', 'java', ['-cp', `${cp}:${strip}`, 'binarytest.StripSourceKt', helper, noSource]);
inspect('missing-source', [entry, noSource], 'reject:no SourceFile attribute');
const bootstrap = join(work, 'bootstrap.jar');
run('bootstrap-build', 'bash', [compiler, '-Xserialize-ir=inline', join(here, 'Bootstrap.kt'), '-d', bootstrap]);
const cycleHelper = join(work, 'cycle-helper.jar');
run('cycle-helper-build', 'bash', [compiler, '-classpath', `${cp}:${bootstrap}`, '-Xserialize-ir=inline', join(here, 'CycleHelper.kt'), '-d', cycleHelper]);
const cycleEntry = join(work, 'cycle-entry.jar');
run('cycle-entry-build', 'bash', [compiler, '-classpath', `${cp}:${cycleHelper}`, '-Xserialize-ir=inline', join(here, 'Entry.kt'), '-d', cycleEntry]);
inspect('cycle', [cycleEntry, cycleHelper], 'reject:serialized inline dependency cycle:');
console.log('PASS focused frontend only; no public CLI build or target runtime in this mode');
