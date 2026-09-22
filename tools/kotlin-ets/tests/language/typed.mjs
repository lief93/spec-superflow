import { mkdirSync, mkdtempSync, readdirSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../..');
mkdirSync(join(here, '.work'), { recursive: true });
const work = mkdtempSync(join(here, '.work/typed-'));
console.log(`Evidence: ${work}`);
function run(label, command, args) {
  const result = spawnSync(command, args, { encoding: 'utf8' });
  writeFileSync(join(work, `${label}.json`), JSON.stringify({ command, args, status: result.status,
    stdout: result.stdout, stderr: result.stderr }, null, 2));
  if (label !== 'classpath') process.stdout.write(result.stdout ?? '');
  process.stderr.write(result.stderr ?? '');
  if (result.error) throw result.error;
  if (result.status !== 0) process.exit(result.status || 1);
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
const jar = join(work, 'typed-tests.jar');
run('compile', 'bash', [compiler, ...kotlinFiles(join(root, 'src/target')).filter(path => !path.endsWith('Printer.kt')),
  ...kotlinFiles(join(root, 'src/core')), ...kotlinFiles(join(root, 'src/lower')), ...kotlinFiles(join(root, 'src/language')),
  ...kotlinFiles(join(root, 'src/stdlib')),
  join(here, 'TypedLoweringTest.kt'), '-d', jar]);
run('test', 'java', ['-cp', `${jar}:${classpath}`, 'dev.ets.TypedLoweringTestKt', join(here, 'TypedSlice.kt'), classpath, join(here, 'TypedHelper.kt')]);
