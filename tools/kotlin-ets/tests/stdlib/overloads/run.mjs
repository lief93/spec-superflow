import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { copyFileSync, existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const mode = process.argv[2];
assert.ok(['typed', 'public'].includes(mode), 'Choose typed or public');
assert.equal(process.env.KOTLIN_ETS_OVERLOAD_SLOT, mode, 'Requires a main-approved matching serialized build slot');
const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../../..');
mkdirSync(join(here, '.work'), { recursive: true });
const work = mkdtempSync(join(here, '.work/' + mode + '-'));
console.log(`Overload stdlib evidence: ${work}`);
const hash = file => createHash('sha256').update(readFileSync(file)).digest('hex');
function kotlinFiles(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap(entry => entry.isDirectory()
    ? kotlinFiles(join(directory, entry.name)) : entry.name.endsWith('.kt') ? [join(directory, entry.name)] : []).sort();
}
const production = mode === 'public' ? kotlinFiles(join(root, 'src')) : [
  ...kotlinFiles(join(root, 'src/target')), join(root, 'src/output/Modules.kt'),
  join(root, 'src/stdlib/StandardLibraryDependencies.kt'), join(root, 'src/stdlib/StandardLibrarySupport.kt'),
];
const paths = [...production, ...kotlinFiles(join(here, 'fixtures')), ...kotlinFiles(join(here, 'negative')),
  ...['OverloadRuntimeContract.kt', 'OverloadBindings.kt', 'OverloadOracle.kt', 'run.mjs', 'host.mjs', 'cases.json', 'SdkConsumer.ets'].map(name => join(here, name)),
  join(root, 'kotlin-ets'), join(root, 'tests/stdlib/compiler.sh'), join(root, 'tests/stdlib/runtime-assertions.mjs')];
const inputs = paths.map(path => {
  const snapshot = join(work, 'frozen', relative(root, path));
  mkdirSync(dirname(snapshot), { recursive: true });
  const sha256 = hash(path);
  copyFileSync(path, snapshot);
  assert.equal(hash(snapshot), sha256, `Input changed while freezing ${path}`);
  return { path, snapshot, sha256 };
});
const frozen = path => inputs.find(input => input.path === path).snapshot;
const manifest = { work, mode, inputs, commands: [], passed: false, sdk: false };
const record = () => writeFileSync(join(work, 'result.json'), JSON.stringify(manifest, null, 2) + '\n');
const env = { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' };
function run(label, executable, args, failure = false) {
  const result = spawnSync(executable, args, { env, encoding: 'utf8', timeout: 300000, maxBuffer: 16 * 1024 * 1024 });
  writeFileSync(join(work, label + '.stdout'), result.stdout ?? '');
  writeFileSync(join(work, label + '.stderr'), result.stderr ?? '');
  manifest.commands.push({ label, executable, args, status: result.status, signal: result.signal, error: result.error?.message });
  record();
  assert.equal(result.signal, null, `${label}: interrupted`);
  assert.equal(result.error, undefined, `${label}: child process error`);
  if (failure) assert.ok(Number.isInteger(result.status) && result.status !== 0, `${label}: expected rejection`);
  else assert.equal(result.status, 0, `${label}: ${result.stdout}\n${result.stderr}`);
  return result.stdout;
}
record();
const compiler = frozen(join(root, 'tests/stdlib/compiler.sh'));
const cp = run('classpath', 'bash', [compiler, '--classpath']).trim();
const jar = join(work, 'test.jar');
manifest.output = join(work, 'modules');
if (mode === 'typed') {
  run('compile', 'bash', [compiler, ...production.map(frozen), frozen(join(here, 'OverloadRuntimeContract.kt')), '-d', jar]);
  process.stdout.write(run('typed', 'java', ['-cp', `${cp}:${jar}`, 'dev.ets.tests.overloadruntime.OverloadRuntimeContractKt', manifest.output]));
} else {
  const sources = kotlinFiles(join(here, 'fixtures')).map(frozen);
  run('jvm-compile', 'bash', [compiler, ...sources, frozen(join(here, 'OverloadOracle.kt')), '-d', jar]);
  run('jvm', 'java', ['-cp', `${cp}:${jar}`, 'stdliboverloads.OverloadOracleKt']);
  const probe = join(work, 'producer.jar');
  run('producer-compile', 'bash', [compiler, ...production.map(frozen), frozen(join(here, 'OverloadBindings.kt')), '-d', probe]);
  manifest.producer = join(work, 'producer');
  process.stdout.write(run('producer', 'java', ['-cp', `${cp}:${probe}`, 'dev.ets.tests.overloadbindings.OverloadBindingsKt',
    manifest.producer, '-no-stdlib', '-no-reflect', '-classpath', cp, ...sources]));
  run('cli', 'bash', [frozen(join(root, 'kotlin-ets')), '--mode', 'language', '--out-dir', manifest.output, ...sources]);
  process.stdout.write(run('host', process.execPath, [frozen(join(here, 'host.mjs')), manifest.output, join(work, 'jvm.stdout'), manifest.producer]));
  const rejectedOutput = join(work, 'rejected-inherited');
  const diagnostic = JSON.parse(run('inherited-negative', 'bash', [frozen(join(root, 'kotlin-ets')), '--mode', 'language', '--out-dir',
    rejectedOutput, frozen(join(here, 'negative/Inherited.kt'))], true));
  assert.equal(diagnostic.code, 'UNSUPPORTED');
  assert.match(diagnostic.message, /overload/i);
  assert.equal(diagnostic.source.file, frozen(join(here, 'negative/Inherited.kt')));
  assert.ok(diagnostic.source.start >= 0 && diagnostic.source.end > diagnostic.source.start);
  assert.ok(!existsSync(rejectedOutput), 'Unsupported inherited overload must publish no output');
}
for (const input of inputs) {
  assert.equal(hash(input.snapshot), input.sha256, `Frozen input changed: ${input.path}`);
  assert.equal(hash(input.path), input.sha256, `Source changed during run: ${input.path}`);
}
manifest.modules = readdirSync(manifest.output).sort().map(name => ({ name, sha256: hash(join(manifest.output, name)) }));
manifest.passed = true;
record();
