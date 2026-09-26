import assert from 'node:assert/strict';
import { existsSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../../..');
const work = mkdtempSync(join(tmpdir(), 'kotlin-ets-navigation-'));
const probe = process.env.KOTLIN_ETS_PROBE ?? '/tmp/kotlin-official-frontend-probe-06';
const classpath = JSON.parse(readFileSync(join(probe, 'classpath.json'), 'utf8'));
const classpathFile = join(work, 'classpath.txt');
writeFileSync(classpathFile, classpath.join('\n') + '\n');

const output = join(work, 'NavigationPage.ets');
const result = spawnSync('bash', [join(root, 'kotlin-ets'), '--mode', 'page',
  '--unsupported-policy', 'error', '--entry', 'navigation.NavigationPage',
  '--classpath-file', classpathFile, '--out', output, join(here, 'Page.kt')], {
  encoding: 'utf8', maxBuffer: 16 * 1024 * 1024,
  env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' },
});
writeFileSync(join(work, 'command.json'), JSON.stringify({ status: result.status,
  stdout: result.stdout, stderr: result.stderr }, null, 2));
assert.equal(result.status, 0, result.stdout + result.stderr);
assert.equal(existsSync(output), true);

const selectionLine = result.stderr.split('\n').find(line => line.startsWith('{"event":"source-selection"'));
assert.ok(selectionLine, 'source selection report');
const selection = JSON.parse(selectionLine);
assert.ok(selection.excluded.some(item => item.symbol === 'navigation.RegisterScreenRoute'),
  'target-owned route identity must not retain its source implementation');

const code = readFileSync(output, 'utf8');
assert.match(code, /router\.pushNamedRoute\(\{ name: "RegisterScreenRoute" \}\)/);
assert.match(code, /private readonly label: string = "Register";/,
  'ordinary remember values become typed component-instance fields');
assert.match(code, /Text\(this\.label\)/);
assert.doesNotMatch(code, /sourceOnlyImplementation|class RegisterScreenRoute/);
console.log(JSON.stringify({ ok: true, evidence: work, output }));
