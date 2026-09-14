import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../..');
mkdirSync(join(here, '.work'), { recursive: true });
const work = mkdtempSync(join(here, '.work/experiment-'));
console.log(`Evidence: ${work}`);
function run(label, command, args, expected = 0) {
  const result = spawnSync(command, args, { encoding: 'utf8', timeout: 120000 });
  writeFileSync(join(work, `${label}.json`), JSON.stringify({ command, args, status: result.status,
    stdout: result.stdout, stderr: result.stderr, error: result.error?.message }, null, 2));
  if (label !== 'classpath') process.stdout.write(result.stdout ?? '');
  if (result.error) throw result.error;
  if (expected !== null) assert.equal(result.status, expected, `${label}: ${result.stderr}`);
  return result;
}
const compiler = join(root, 'tests/stdlib/compiler.sh');
const cp = run('classpath', 'bash', [compiler, '--classpath']).stdout.trim();
const librarySource = join(here, 'BinaryLibrary.kt');
const application = join(here, 'Application.kt');
const jars = ['signature', 'serialized'].map(kind => join(work, `${kind}.jar`));
run('signature-build', 'bash', [compiler, librarySource, '-d', jars[0]]);
run('serialized-build', 'bash', [compiler, '-Xserialize-ir=inline', librarySource, '-d', jars[1]]);
const hash = file => createHash('sha256').update(readFileSync(file)).digest('hex');
writeFileSync(join(work, 'inputs.json'), JSON.stringify([librarySource, application, ...jars].map(path => ({ path, sha256: hash(path) })), null, 2));
const oracle = join(work, 'oracle.jar');
run('oracle-build', 'bash', [compiler, '-classpath', `${cp}:${jars[1]}`, application, join(here, 'JvmOracle.kt'), '-d', oracle]);
run('oracle-run', 'java', ['-cp', `${cp}:${jars[1]}:${oracle}`, 'binaryapplication.JvmOracleKt']);
const probe = join(work, 'probe.jar');
run('probe-build', 'bash', [compiler, join(root, 'src/core/OfficialLowerings.kt'), join(here, 'BinaryProbe.kt'), '-d', probe]);
run('signature-probe', 'java', ['-cp', `${cp}:${probe}`, 'dev.ets.BinaryProbeKt', application, `${cp}:${jars[0]}`, work, 'signature']);
for (const mode of ['serialized', 'registered', 'linked']) {
  const directory = join(work, mode);
  mkdirSync(directory);
  const result = run(`${mode}-probe`, 'java', ['-cp', `${cp}:${probe}`, 'dev.ets.BinaryProbeKt',
    application, `${cp}:${jars[1]}`, directory, mode], mode === 'registered' ? 0 : 1);
  if (mode === 'serialized') assert.match(result.stderr, /Deserialization must populate the actual resolved call declaration/);
  if (mode === 'registered') assert.match(result.stdout, /unbound=5/);
  if (mode === 'linked') {
    assert.match(result.stdout, /unbound=0/);
    assert.match(result.stderr, /Unknown file/);
    assert.match(result.stderr, /FunctionInlining\$CallInlining\.inlineFunction/);
  }
}
console.log('PASS blocker characterization only: real serialized bytes/body do NOT establish a usable official inliner input');
