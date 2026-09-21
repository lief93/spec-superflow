import assert from 'node:assert/strict';
import { mkdirSync, mkdtempSync, readdirSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../..');
mkdirSync(join(here, '.work'), { recursive: true });
const work = mkdtempSync(join(here, '.work/pipeline-'));
console.log(`Evidence: ${work}`);
function run(label, command, args) {
  const result = spawnSync(command, args, { encoding: 'utf8', timeout: 300000, maxBuffer: 16 * 1024 * 1024 });
  writeFileSync(join(work, `${label}.json`), JSON.stringify({ command, args, status: result.status,
    stdout: result.stdout, stderr: result.stderr }, null, 2));
  if (result.error) throw result.error;
  assert.equal(result.status, 0, `${label}: ${result.stdout}\n${result.stderr}`);
  process.stdout.write(result.stdout ?? '');
  return result.stdout.trim();
}
function kotlinFiles(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap(entry => {
    const path = join(directory, entry.name);
    return entry.isDirectory() ? kotlinFiles(path)
      : entry.name.endsWith('.kt') && entry.name !== 'Main.kt' ? [path] : [];
  }).sort();
}
const compiler = join(root, 'tests/stdlib/compiler.sh');
const classpath = run('classpath', 'bash', [compiler, '--classpath']);
const jar = join(work, 'pipeline.jar');
const sources = [
  ...kotlinFiles(join(root, 'src/core')),
  ...kotlinFiles(join(root, 'src/lower')),
  ...kotlinFiles(join(root, 'src/language')),
  ...['Tree.kt', 'TypeSubstitution.kt', 'Validator.kt', 'Traversal.kt'].map(name => join(root, 'src/target', name)),
  ...kotlinFiles(join(root, 'src/stdlib')),
];
run('compile', 'bash', [compiler, ...sources, join(here, 'PipelineEvidence.kt'), '-d', jar]);
console.log(run('pipeline', 'java', ['-cp', `${jar}:${classpath}`, 'dev.ets.PipelineEvidenceKt',
  join(here, 'Concatenation.kt'), classpath, work]));
