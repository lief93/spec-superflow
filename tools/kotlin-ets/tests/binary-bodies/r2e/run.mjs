// Serialized build slot required. Compile a frozen focused snapshot, never the moving whole backend.
import assert from 'node:assert/strict';
import { cpSync, existsSync, mkdirSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { basename, dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { compiler, core, harness, identities, root, hash, sources } from '../r2b/support.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const { work, run } = harness(join(here, '.work'));
process.env.JAVA_HOME = '/Applications/Android Studio.app/Contents/jbr/Contents/Home';
const snapshot = join(work, 'snapshot');
mkdirSync(snapshot);
const sourceRoot = process.env.KOTLIN_ETS_SOURCE_ROOT ?? join(root, 'src');
const inputs = [...core.map(path => join(sourceRoot, relative(join(root, 'src'), path))),
  ...sources(join(sourceRoot, 'target')), join(here, 'Evidence.kt')];
const frozen = inputs.map(path => {
  const copy = join(snapshot, basename(path));
  cpSync(path, copy);
  return copy;
});
const production = identities(inputs).map((input, index) => ({ ...input, snapshot: frozen[index] }));
writeFileSync(join(work, 'identity.json'), JSON.stringify(production, null, 2));
const cp = run('classpath', 'bash', [compiler, '--classpath']).trim();
const producer = join(work, 'producer-source');
cpSync(join(here, 'library'), producer, { recursive: true });
const producerIdentity = identities(readdirSync(producer).map(name => join(producer, name)));
writeFileSync(join(work, 'producer-source.json'), JSON.stringify(producerIdentity, null, 2));
const library = join(work, 'members.jar');
run('member-build', 'bash', [compiler, '-Xserialize-ir=inline', join(producer, 'Members.kt'), '-d', library]);
run('signature-build', 'bash', [compiler, join(producer, 'Members.kt'), '-d', join(work, 'signature.jar')]);
run('boundaries-build', 'bash', [compiler, '-Xserialize-ir=inline', join(producer, 'Unsupported.kt'), '-d', join(work, 'boundaries.jar')]);
rmSync(producer, { recursive: true });
assert.equal(existsSync(producer), false);
const consumer = join(work, 'consumer');
mkdirSync(consumer);
for (const name of ['Application.kt', 'Oracle.kt']) cpSync(join(here, name), join(consumer, name));
const application = join(consumer, 'Application.kt');
const oracle = join(work, 'oracle.jar');
run('oracle-build', 'bash', [compiler, '-classpath', `${cp}:${library}`, application, join(consumer, 'Oracle.kt'), '-d', oracle]);
const expected = run('jvm', 'java', ['-cp', `${cp}:${library}:${oracle}`, 'memberconsumer.OracleKt']).trim().split('\n');
assert.deepEqual(expected, ['1/7/10/7/-6/3/fallback/text/18/RBALRCDPREFRHGIRJK',
  '1/7/7/7/-6/0/fallback/text/18/RBALRCDPREFRHGIRJK',
  '1/7/-2147483640/7/-6/-2147483647/fallback/text/18/RBALRCDPREFRHGIRJK']);
const evidence = join(work, 'evidence.jar');
run('evidence-build', 'bash', [compiler, ...frozen, '-d', evidence]);
function inspect(name, jar, source, mode) {
  const directory = join(work, name);
  mkdirSync(directory);
  console.log(run(name, 'java', ['-cp', `${cp}:${evidence}`, 'dev.ets.r2e.EvidenceKt', `${cp}:${jar}`, source,
    directory, ...(mode ? [mode] : [])]).trim());
}
inspect('member-evidence', library, application);
inspect('signature-evidence', join(work, 'signature.jar'), application, 'signature-only');
const boundaries = [
  ['Stateful', 'receiver.apply(value)', 'class state is not supported'],
  ['OpenMember', 'receiver.apply(value)', 'require a non-generic top-level final class'],
  ['GenericMember<Int>', 'receiver.apply(value)', 'require a non-generic top-level final class'],
  ['ReifiedMember', 'receiver.apply(value)', 'unsupported reified binary inline dependency'],
  ['ConstructorMember', 'receiver.apply(value)', 'binary inline constructors are not supported'],
  ['OrdinaryHelperMember', 'receiver.apply(value)', 'unsupported serialized body call'],
];
const negatives = [];
for (const [index, [type, call, message]] of boundaries.entries()) {
  const source = join(consumer, `Boundary${index}.kt`);
  writeFileSync(source, `package memberconsumer\nfun boundary(receiver: memberboundaries.${type}, value: Int): Any = ${call}\n`);
  inspect(`boundary-${index}`, join(work, 'boundaries.jar'), source, `reject:${message}`);
  negatives.push({ name: `boundary-${index}`, jar: 'boundaries.jar', source, message });
}
const strip = join(work, 'strip.jar');
run('strip-build', 'bash', [compiler, join(here, '../StripSource.kt'), '-d', strip]);
run('strip-source', 'java', ['-cp', `${cp}:${strip}`, 'binarytest.StripSourceKt', library, join(work, 'no-source.jar')]);
inspect('no-source-evidence', join(work, 'no-source.jar'), application, 'reject:no SourceFile attribute');
negatives.push({ name: 'no-source', jar: 'no-source.jar', source: application, message: 'no SourceFile attribute' });
assert.ok(production.every(item => hash(item.snapshot) === item.sha256), 'Frozen focused snapshot changed');
writeFileSync(join(work, 'producers.json'), JSON.stringify(identities(readdirSync(work).filter(name => name.endsWith('.jar')).map(name => join(work, name))), null, 2));
writeFileSync(join(work, 'complete.json'), JSON.stringify({ expected, negatives, application, focusedSnapshotUnchanged: true,
  producerSourceAbsent: true, officialInlineBlocks: 14, hostParity: 'pending shared frozen replay' }, null, 2));
console.log('PASS frozen focused member-inline checks; no public backend or SDK claim');
