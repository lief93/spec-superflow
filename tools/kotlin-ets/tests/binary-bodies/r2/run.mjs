// Focused compiler slot required. No public CLI or shared target lowering here.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdirSync, mkdtempSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../../..');
process.env.JAVA_TOOL_OPTIONS = '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC';
process.env.PATH = `/Applications/Android Studio.app/Contents/jbr/Contents/Home/bin:${process.env.PATH}`;
mkdirSync(join(here, '.work'), { recursive: true });
const work = mkdtempSync(join(here, '.work/run-'));
console.log(`Evidence: ${work}`);
const hash = path => createHash('sha256').update(readFileSync(path)).digest('hex');
function run(label, command, args, status = 0) {
  const result = spawnSync(command, args, { encoding: 'utf8', timeout: 300000 });
  writeFileSync(join(work, `${label}.json`), JSON.stringify({ command, args, status: result.status,
    stdout: result.stdout, stderr: result.stderr, error: result.error?.message }, null, 2));
  if (result.error) throw result.error;
  assert.equal(result.status, status, `${label}: ${result.stdout}\n${result.stderr}`);
  return result.stdout + (status ? result.stderr : '');
}
const compiler = join(root, 'tests/stdlib/compiler.sh');
const cp = run('classpath', 'bash', [compiler, '--classpath']).trim();
const sources = ['Direct.kt', 'Entry.kt', 'Helper.kt'];
const library = join(work, 'combined.jar');
run('combined-build', 'bash', [compiler, '-Xserialize-ir=inline', ...sources.map(name => join(here, name)), '-d', library]);
const oracle = join(work, 'oracle.jar');
run('oracle-build', 'bash', [compiler, '-classpath', `${cp}:${library}`, join(here, 'Application.kt'), join(here, 'Oracle.kt'), '-d', oracle]);
const expected = run('jvm', 'java', ['-cp', `${cp}:${library}:${oracle}`, 'genericconsumer.OracleKt']).trim().split('\n');
assert.deepEqual(expected, ['3/5/5/9/6/IDBOIG', '0/2/2/0/6/IDBOIG', '-2147483647/-2147483645/-2147483645/-2147483645/6/IDBOIG']);
const core = ['Frontend.kt', 'Constructors.kt', 'ConstructorDispatch.kt', 'DefaultArguments.kt', 'LibraryInlining.kt', 'BinaryBodies.kt', 'OfficialLowerings.kt', 'LocalDeclarations.kt',
  'ForLoops.kt', 'ExpectedNullability.kt', 'Contract.kt', 'CallCaptures.kt', 'GenericBounds.kt'].map(name => join(root, 'src/core', name));
const evidence = join(work, 'evidence.jar');
writeFileSync(join(work, 'identity.json'), JSON.stringify([...core, ...sources.map(name => join(here, name)), library,
  join(here, 'Application.kt'), join(here, 'Evidence.kt'), join(root, 'src/target/Tree.kt')].map(path => ({ path, sha256: hash(path) })), null, 2));
run('evidence-build', 'bash', [compiler, ...core, join(root, 'src/target/Tree.kt'), join(here, 'Evidence.kt'), '-d', evidence]);
function inspect(name, jars, source = 'Application.kt', mode) {
  const directory = join(work, name);
  mkdirSync(directory);
  return run(name, 'java', ['-cp', `${cp}:${evidence}`, 'dev.ets.r2.EvidenceKt', [cp, ...jars].join(':'),
    join(here, source), directory, ...(mode ? [mode] : [])], process.argv.includes('--red') ? 1 : 0);
}
const first = inspect('combined-evidence', [library]);
if (process.argv.includes('--red')) {
  assert.match(first, /require non-generic top-level inline/);
  console.log('RED captured: real producer/JVM oracle succeed; production rejects actual generic serialized body');
  process.exit(0);
}
console.log(first.trim());
const helper = join(work, 'helper.jar');
run('helper-build', 'bash', [compiler, '-Xserialize-ir=inline', join(here, 'Helper.kt'), '-d', helper]);
const entry = join(work, 'entry.jar');
run('entry-build', 'bash', [compiler, '-classpath', `${cp}:${helper}`, '-Xserialize-ir=inline', join(here, 'Direct.kt'), join(here, 'Entry.kt'), '-d', entry]);
console.log(inspect('second-jar-evidence', [entry, helper]).trim());
run('signature-build', 'bash', [compiler, ...sources.map(name => join(here, name)), '-d', join(work, 'signature.jar')]);
run('signature-helper-build', 'bash', [compiler, join(here, 'Helper.kt'), '-d', join(work, 'signature-helper.jar')]);
for (const name of ['Reified', 'Member', 'Multifile']) {
  run(`${name}-build`, 'bash', [compiler, '-Xserialize-ir=inline', join(here, `${name}.kt`), '-d', join(work, `${name}.jar`)]);
}
const strip = join(work, 'strip.jar');
run('strip-build', 'bash', [compiler, join(here, '../StripSource.kt'), '-d', strip]);
const noSource = join(work, 'no-source-helper.jar');
run('strip-source', 'java', ['-cp', `${cp}:${strip}`, 'binarytest.StripSourceKt', helper, noSource]);
for (const [name, jars, source, mode] of [
  ['signature-evidence', ['signature.jar'], 'Application.kt', 'signature-only'],
  ['missing-body-evidence', ['entry.jar', 'signature-helper.jar'], 'Application.kt', 'reject:missing serialized IR body for dependency'],
  ['missing-jar-evidence', ['entry.jar'], 'Application.kt', 'reject:unlinked serialized dependencies:'],
  ['missing-source-evidence', ['entry.jar', 'no-source-helper.jar'], 'Application.kt', 'reject:no SourceFile attribute'],
  ['reified-evidence', ['Reified.jar'], 'ReifiedApplication.kt', 'reject:unsupported reified binary inline dependency'],
  ['member-evidence', ['Member.jar'], 'MemberApplication.kt', 'reject:members are unsupported'],
  ['multifile-evidence', ['Multifile.jar'], 'MultifileApplication.kt', 'reject:unsupported serialized dependency format MULTIFILE_CLASS_PART'],
]) console.log(inspect(name, jars.map(jar => join(work, jar)), source, mode).trim());
writeFileSync(join(work, 'producers.json'), JSON.stringify([
  ...readdirSync(work).filter(name => name.endsWith('.jar')).map(name => join(work, name)),
  ...readdirSync(here).filter(name => name.endsWith('.kt')).map(name => join(here, name)),
].map(path => ({ path, sha256: hash(path) })), null, 2));
writeFileSync(join(work, 'complete.json'), JSON.stringify({ focused: true, genericInlineBlocksPerLayout: 5, layouts: 2, boundaryCases: 7, expected }));
console.log('PASS focused generic binary provenance and seven boundaries; public CLI awaits frozen build slot');
