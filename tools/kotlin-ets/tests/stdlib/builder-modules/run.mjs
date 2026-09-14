import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { copyFileSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

assert.equal(process.env.KOTLIN_ETS_BUILDER_SLOT, '1', 'Requires a main-approved isolated target build slot');
const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../../..');
mkdirSync(join(here, '.work'), { recursive: true });
const work = mkdtempSync(join(here, '.work/run-'));
console.log(`Global builder runtime evidence: ${work}`);
const hash = file => createHash('sha256').update(readFileSync(file)).digest('hex');
const paths = [
  ...readdirSync(join(root, 'src/target')).filter(name => name.endsWith('.kt')).sort().map(name => `src/target/${name}`),
  'src/output/Modules.kt', 'src/stdlib/StandardLibrarySupport.kt', 'src/stdlib/StandardLibraryDependencies.kt',
  'tests/stdlib/builder-modules/BuilderRuntimeFixture.kt', 'tests/stdlib/builder-modules/BuilderRuntimeContract.kt',
];
const inputs = paths.map(relative => {
  const path = join(root, relative), snapshot = join(work, 'frozen', relative);
  mkdirSync(dirname(snapshot), { recursive: true });
  const sha256 = hash(path);
  copyFileSync(path, snapshot);
  assert.equal(hash(snapshot), sha256, `Input changed while freezing ${relative}`);
  return { path, snapshot, sha256 };
});
const manifest = { work, inputs, commands: [], passed: false, level: 'typed target/module/runtime contract; not public CLI or SDK' };
const record = () => writeFileSync(join(work, 'result.json'), JSON.stringify(manifest, null, 2) + '\n');
const env = { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' };
function run(label, executable, args) {
  const result = spawnSync(executable, args, { env, encoding: 'utf8', timeout: 300000, maxBuffer: 16 * 1024 * 1024 });
  writeFileSync(join(work, label + '.stdout'), result.stdout ?? '');
  writeFileSync(join(work, label + '.stderr'), result.stderr ?? '');
  manifest.commands.push({ label, executable, args, status: result.status, signal: result.signal, error: result.error?.message });
  record();
  assert.equal(result.status, 0, `${label}: ${result.stdout}\n${result.stderr}`);
  return result.stdout;
}
record();
const compiler = join(root, 'tests/stdlib/compiler.sh');
run('compile', 'bash', [compiler, ...inputs.map(input => input.snapshot), '-d', join(work, 'test.jar')]);
const cp = run('classpath', 'bash', [compiler, '--classpath']).trim();
manifest.output = join(work, 'modules');
const stdout = run('contract', 'java', ['-cp', `${cp}:${join(work, 'test.jar')}`,
  'dev.ets.tests.builderruntime.BuilderRuntimeContractKt', manifest.output]);
for (const input of inputs) {
  assert.equal(hash(input.snapshot), input.sha256, `Frozen input changed: ${input.path}`);
  assert.equal(hash(input.path), input.sha256, `Source changed during run: ${input.path}`);
}
manifest.modules = readdirSync(manifest.output).sort().map(name => ({ name, sha256: hash(join(manifest.output, name)) }));
manifest.passed = true;
record();
process.stdout.write(stdout);
