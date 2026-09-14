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
const implementationRoot = process.env.KOTLIN_ETS_SOURCE_ROOT ?? join(root, 'src');
const implementations = readdirSync(implementationRoot, { recursive: true }).filter(path => path.endsWith('.kt'))
  .map(path => join(implementationRoot, path)).sort();
const source = join(here, 'GenericHeritage.kt'), probe = join(here, 'GenericHeritageProbe.kt');
const hash = path => createHash('sha256').update(readFileSync(path)).digest('hex');
const result = { inputs: [...implementations, source, probe, fileURLToPath(import.meta.url)].map(path => ({ path, sha256: hash(path) })), commands: [] };
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
const cp = run('classpath', 'bash', [compiler, '--classpath']), jar = join(work, 'probe.jar');
run('compile', 'bash', [compiler, ...implementations, probe, '-d', jar]);
console.log(run('probe', 'java', ['-cp', `${jar}:${cp}`, 'dev.ets.GenericHeritageProbeKt', source, cp, work]));
for (const input of result.inputs) assert.equal(hash(input.path), input.sha256, `Changed during verification: ${input.path}`);
result.output = { path: join(work, 'GenericHeritage.ets'), sha256: hash(join(work, 'GenericHeritage.ets')) };
result.passed = true; record();
