import { mkdirSync, mkdtempSync, writeFileSync } from 'node:fs';
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
const compiler = join(root, 'tests/stdlib/compiler.sh');
const classpath = run('classpath', 'bash', [compiler, '--classpath']);
const jar = join(work, 'typed-tests.jar');
run('compile', 'bash', [compiler, ...['target/Tree.kt', 'target/TypeSubstitution.kt', 'target/Validator.kt', 'target/Traversal.kt', 'core/Contract.kt',
  'core/Frontend.kt', 'core/Constructors.kt', 'core/DefaultArguments.kt', 'core/OfficialLowerings.kt', 'core/ExpectedNullability.kt', 'core/LibraryInlining.kt', 'core/BinaryBodies.kt', 'core/LocalDeclarations.kt', 'core/ForLoops.kt', 'language/LanguageLowering.kt', 'language/OverloadNaming.kt', 'language/ClassNaming.kt'].map(file => join(root, 'src', file)),
  join(here, 'TypedLoweringTest.kt'), '-d', jar]);
run('test', 'java', ['-cp', `${jar}:${classpath}`, 'dev.ets.TypedLoweringTestKt', join(here, 'TypedSlice.kt'), classpath, join(here, 'TypedHelper.kt')]);
