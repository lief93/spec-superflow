import assert from 'node:assert/strict';
import { mkdirSync, mkdtempSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const here = dirname(fileURLToPath(import.meta.url)), root = resolve(here, '../..');
mkdirSync(join(here, '.work'), { recursive: true });
const work = mkdtempSync(join(here, '.work/typed-'));
console.log(`Evidence: ${work}`);
const env = { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' };
function run(label, command, args) {
  const result = spawnSync(command, args, { encoding: 'utf8', timeout: 600000, maxBuffer: 16 * 1024 * 1024, env });
  writeFileSync(join(work, label + '.json'), JSON.stringify({ command, args, status: result.status,
    JAVA_TOOL_OPTIONS: env.JAVA_TOOL_OPTIONS, stdout: result.stdout, stderr: result.stderr }, null, 2));
  assert.equal(result.error, undefined);
  assert.equal(result.status, 0, result.stdout + result.stderr);
  return result.stdout.trim();
}
function sources(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap(entry => entry.isDirectory()
    ? sources(join(directory, entry.name)) : entry.name.endsWith('.kt') ? [join(directory, entry.name)] : []).sort();
}
const compiler = join(root, 'tests/stdlib/compiler.sh');
const hash = path => createHash('sha256').update(readFileSync(path)).digest('hex');
const inputs = [...sources(join(root, 'src')), join(here, 'IterationEvidence.kt'), join(here, 'Iteration.kt')]
  .map(path => ({ path, sha256: hash(path) }));
writeFileSync(join(work, 'inputs.json'), JSON.stringify(inputs, null, 2));
const cp = run('classpath', 'bash', [compiler, '--classpath']);
const jar = join(work, 'evidence.jar');
run('compile', 'bash', [compiler, ...sources(join(root, 'src')), join(here, 'IterationEvidence.kt'), '-d', jar]);
console.log(run('test', 'java', ['-cp', `${jar}:${cp}`, 'dev.ets.IterationEvidenceKt', join(here, 'Iteration.kt'), cp, work]));
for (const input of inputs) assert.equal(hash(input.path), input.sha256, `Changed during verification: ${input.path}`);
