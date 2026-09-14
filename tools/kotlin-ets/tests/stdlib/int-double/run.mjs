import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { copyFileSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const mode = process.argv[2];
assert.ok(['symbols', 'public'].includes(mode));
assert.equal(process.env.KOTLIN_ETS_CONVERSION_SLOT, mode, 'Exclusive main-approved build slot required');
const here = dirname(fileURLToPath(import.meta.url)), root = resolve(here, '../../..');
mkdirSync(join(here, '.work'), { recursive: true });
const work = mkdtempSync(join(here, '.work/' + mode + '-'));
console.log(`Int.toDouble evidence: ${work}`);
function sources(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap(entry => entry.isDirectory() ? sources(join(directory, entry.name))
    : entry.name.endsWith('.kt') ? [join(directory, entry.name)] : []).sort();
}
const production = sources(join(root, 'src'));
const hash = file => createHash('sha256').update(readFileSync(file)).digest('hex');
const paths = [...production, ...['IntDouble.kt', 'Rejected.kt', 'Oracle.kt', 'Symbols.kt', 'run.mjs', 'host.mjs'].map(name => join(here, name)),
  join(root, 'kotlin-ets'), join(root, 'tests/stdlib/compiler.sh'), join(root, 'tests/stdlib/runtime-assertions.mjs')];
const inputs = paths.map(path => {
  const snapshot = join(work, 'frozen', relative(root, path)), sha256 = hash(path);
  mkdirSync(dirname(snapshot), { recursive: true }); copyFileSync(path, snapshot);
  assert.equal(hash(snapshot), sha256);
  return { path, snapshot, sha256 };
});
const frozen = path => inputs.find(input => input.path === path).snapshot;
const manifest = { mode, work, inputs, commands: [], passed: false, sdk: false };
const record = () => writeFileSync(join(work, 'result.json'), JSON.stringify(manifest, null, 2));
function run(label, command, args) {
  const result = spawnSync(command, args, { encoding: 'utf8', timeout: 300000, maxBuffer: 16 * 1024 * 1024,
    env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' } });
  writeFileSync(join(work, label + '.stdout'), result.stdout ?? '');
  writeFileSync(join(work, label + '.stderr'), result.stderr ?? '');
  manifest.commands.push({ label, command, args, status: result.status, signal: result.signal, error: result.error?.message }); record();
  assert.equal(result.status, 0, `${label}: ${result.stdout}\n${result.stderr}`);
  return result.stdout;
}
record();
const compiler = frozen(join(root, 'tests/stdlib/compiler.sh'));
const cp = run('classpath', 'bash', [compiler, '--classpath']).trim(), jar = join(work, 'test.jar');
if (mode === 'symbols') {
  run('compile', 'bash', [compiler, ...production.map(frozen), frozen(join(here, 'Symbols.kt')), '-d', jar]);
  process.stdout.write(run('symbols', 'java', ['-cp', cp + ':' + jar, 'dev.ets.tests.intdouble.SymbolsKt', '-no-stdlib', '-no-reflect',
    '-classpath', cp, frozen(join(here, 'IntDouble.kt')), frozen(join(here, 'Rejected.kt'))]));
} else {
  run('jvm-compile', 'bash', [compiler, frozen(join(here, 'IntDouble.kt')), frozen(join(here, 'Oracle.kt')), '-d', jar]);
  run('jvm', 'java', ['-cp', cp + ':' + jar, 'intdouble.OracleKt']);
  manifest.output = join(work, 'IntDouble.ets');
  run('cli', 'bash', [frozen(join(root, 'kotlin-ets')), '--mode', 'language', '--out', manifest.output, frozen(join(here, 'IntDouble.kt'))]);
  process.stdout.write(run('host', process.execPath, [frozen(join(here, 'host.mjs')), manifest.output, join(work, 'jvm.stdout')]));
  manifest.outputSha256 = hash(manifest.output);
}
for (const input of inputs) {
  assert.equal(hash(input.path), input.sha256, `Live input changed: ${input.path}`);
  assert.equal(hash(input.snapshot), input.sha256, `Snapshot changed: ${input.path}`);
}
manifest.passed = true; record();
