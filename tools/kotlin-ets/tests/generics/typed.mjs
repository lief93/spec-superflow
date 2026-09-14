import assert from 'node:assert/strict';
import { mkdirSync, mkdtempSync, writeFileSync, readdirSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../..');
mkdirSync(join(here, '.work'), { recursive: true });
const work = mkdtempSync(join(here, '.work/typed-'));
console.log(`Evidence: ${work}`);
function run(label, command, args) {
  const result = spawnSync(command, args, { encoding: 'utf8', timeout: 240000 });
  writeFileSync(join(work, label + '.json'), JSON.stringify({ command, args, status: result.status,
    stdout: result.stdout, stderr: result.stderr }, null, 2));
  assert.equal(result.error, undefined);
  assert.equal(result.status, 0, result.stdout + result.stderr);
  return result.stdout.trim();
}
function sources(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap(entry => entry.isDirectory()
    ? sources(join(directory, entry.name)) : entry.name.endsWith('.kt') ? [join(directory, entry.name)] : []).sort();
}
const compiler = join(root, 'tests/stdlib/compiler.sh');
const cp = run('classpath', 'bash', [compiler, '--classpath']);
const jar = join(work, 'typed.jar');
run('compile', 'bash', [compiler, ...sources(join(root, 'src')), join(here, 'TypedGenerics.kt'), '-d', jar]);
console.log(run('test', 'java', ['-cp', `${jar}:${cp}`, 'dev.ets.tests.generics.TypedGenericsKt', cp,
  join(here, 'Functions.kt'), join(here, 'Classes.kt'), join(here, 'LocalGeneric.kt')]));
