import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {mkdtempSync, readFileSync, writeFileSync, existsSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
const launcher = fileURLToPath(new URL('../../../kotlin-ets', import.meta.url));
const source = fileURLToPath(new URL('./ModifierLocal.kt', import.meta.url));
const root = mkdtempSync(join(tmpdir(), 'kotlin-ets-modifier-local-'));
assert.ok(process.argv[2], 'Pass real Compose classpath.txt');
for (const [entry, strict] of [['PrivateModifier', false], ['SharedModifier', false], ['PrivateModifier', true]]) {
  const output = join(root, entry + (strict ? '-strict' : '') + '.ets');
  const result = spawnSync('bash', [launcher, '--entry', 'degradation.' + entry, '--classpath-file', process.argv[2],
    '--out', output, ...(strict ? ['--unsupported-policy', 'error'] : []), source], {
    encoding: 'utf8', maxBuffer: 20 * 1024 * 1024,
    env: {...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC'},
  });
  writeFileSync(output + '.log', result.stdout + result.stderr);
  assert.equal(result.status, 2, result.stdout + result.stderr);
  const report = JSON.parse(readFileSync(output + '.diagnosis.json', 'utf8'));
  assert.equal(existsSync(output), false);
  assert.equal(report.degradationCount, 0);
  assert.match(report.blockingFailure.message, /verticalScroll|BoxWithConstraints/);
}
console.log(JSON.stringify({ok: true, root}));
