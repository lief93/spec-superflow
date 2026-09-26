import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdirSync, mkdtempSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const here = dirname(fileURLToPath(import.meta.url)), root = resolve(here, '../../..');
mkdirSync(join(here, '.work'), { recursive: true });
const work = mkdtempSync(join(here, '.work/probe-'));
console.log(`Evidence: ${work}`);
const sourceFiles = ['Widgets.kt', 'Screen.kt', 'Services.kt'].map(name => join(here, name));
const implementationRoot = process.env.KOTLIN_ETS_SOURCE_ROOT ?? join(root, 'src');
const implementations = readdirSync(implementationRoot, { recursive: true }).filter(path => path.endsWith('.kt'))
  .map(path => join(implementationRoot, path)).sort();
const hash = path => createHash('sha256').update(readFileSync(path)).digest('hex');
const inputs = [...implementations, ...sourceFiles, join(here, 'OwnershipProbe.kt')]
  .map(path => ({ path, sha256: hash(path) }));
const result = { inputs, commands: [] };
const record = () => writeFileSync(join(work, 'result.json'), JSON.stringify(result, null, 2));
const env = { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' };
function run(label, command, args) {
  const value = spawnSync(command, args, { env, encoding: 'utf8', timeout: 600000, maxBuffer: 16 * 1024 * 1024 });
  writeFileSync(join(work, label + '.stdout'), value.stdout ?? '');
  writeFileSync(join(work, label + '.stderr'), value.stderr ?? '');
  result.commands.push({ label, command, args, status: value.status }); record();
  assert.equal(value.error, undefined);
  assert.equal(value.status, 0, value.stdout + value.stderr);
  return value.stdout.trim();
}
const compiler = join(root, 'tests/stdlib/compiler.sh');
const cp = run('classpath', 'bash', [compiler, '--classpath']);
const uiCp = JSON.parse(readFileSync(join(process.env.KOTLIN_ETS_PROBE ?? '/tmp/kotlin-official-frontend-probe-06', 'classpath.json'))).join(':');
const jar = join(work, 'probe.jar');
run('compile', 'bash', [compiler, ...implementations, join(here, 'OwnershipProbe.kt'), '-d', jar]);
console.log(run('probe', 'java', ['-cp', `${jar}:${cp}`, 'dev.ets.OwnershipProbeKt', uiCp, work, ...sourceFiles]));
for (const input of inputs) assert.equal(hash(input.path), input.sha256, `Changed during verification: ${input.path}`);
result.output = { path: join(work, 'OwnershipPage.ets'), sha256: hash(join(work, 'OwnershipPage.ets')) };
result.modules = readdirSync(join(work, 'modules')).sort().map(name => {
  const path = join(work, 'modules', name);
  return { path, sha256: hash(path) };
});
result.passed = true; record();
console.log('PASS source declaration ownership, explicit callback capture, module emission and source hash guard');
