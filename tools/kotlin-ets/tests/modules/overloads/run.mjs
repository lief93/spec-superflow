import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { copyFileSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../../..');
mkdirSync(join(here, '.work'), { recursive: true });
const work = mkdtempSync(join(here, '.work/contract-'));
console.log(`Evidence: ${work}`);
const hash = path => createHash('sha256').update(readFileSync(path)).digest('hex');
const paths = [
  ...readdirSync(join(root, 'src/target')).filter(name => name.endsWith('.kt')).sort().map(name => `src/target/${name}`),
  'src/output/Modules.kt', 'src/stdlib/StandardLibrarySupport.kt', 'src/stdlib/StandardLibraryDependencies.kt',
  'tests/modules/generic-heritage/Fixture.kt', 'tests/modules/overloads/OverloadFixture.kt',
  'tests/modules/overloads/OverloadContract.kt',
];
const inputs = paths.map(relative => {
  const path = join(root, relative);
  const snapshot = join(work, 'frozen', relative);
  mkdirSync(dirname(snapshot), { recursive: true });
  const sha256 = hash(path);
  copyFileSync(path, snapshot);
  assert.equal(hash(snapshot), sha256, `Input changed while freezing: ${relative}`);
  return { path, snapshot, sha256 };
});
const manifest = { work, inputs, commands: [], passed: false };
const record = () => writeFileSync(join(work, 'result.json'), JSON.stringify(manifest, null, 2));
const env = { ...process.env, JAVA_TOOL_OPTIONS:
  `${process.env.JAVA_TOOL_OPTIONS ?? ''} -XX:ActiveProcessorCount=2 -XX:+UseSerialGC`.trim() };
function run(label, command, args) {
  const result = spawnSync(command, args, { env, encoding: 'utf8', timeout: 180000, maxBuffer: 16 * 1024 * 1024 });
  writeFileSync(join(work, `${label}.stdout`), result.stdout ?? '');
  writeFileSync(join(work, `${label}.stderr`), result.stderr ?? '');
  manifest.commands.push({ label, command, args, status: result.status, error: result.error?.message });
  record();
  assert.equal(result.error, undefined);
  assert.equal(result.status, 0, result.stdout + result.stderr);
  return result.stdout;
}
record();
const compiler = join(root, 'tests/stdlib/compiler.sh');
run('compile', 'bash', [compiler, ...inputs.map(input => input.snapshot), '-d', join(work, 'test.jar')]);
const cp = run('classpath', 'bash', [compiler, '--classpath']).trim();
manifest.output = join(work, 'modules');
const result = run('contract', 'java', ['-cp', `${cp}:${join(work, 'test.jar')}`, 'dev.ets.OverloadContractKt', manifest.output]);
for (const input of inputs) assert.equal(hash(input.snapshot), input.sha256);
manifest.currentInputsMatchSnapshot = inputs.every(input => hash(input.path) === input.sha256);
manifest.modules = readdirSync(manifest.output).sort().map(name => ({ name, sha256: hash(join(manifest.output, name)) }));
manifest.passed = true;
record();
process.stdout.write(result);
if (!manifest.currentInputsMatchSnapshot) console.log('Source inputs changed during isolated verification; rerun after main freeze.');
