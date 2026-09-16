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
for (const [entry, strict, status] of [['PrivateModifier', false, 0], ['SharedModifier', false, 2], ['PrivateModifier', true, 2]]) {
  const output = join(root, entry + (strict ? '-strict' : '') + '.ets');
  const result = spawnSync('bash', [launcher, '--entry', 'degradation.' + entry, '--classpath-file', process.argv[2],
    '--out', output, ...(strict ? ['--unsupported-policy', 'error'] : []), source], {
    encoding: 'utf8', maxBuffer: 20 * 1024 * 1024,
    env: {...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC'},
  });
  writeFileSync(output + '.log', result.stdout + result.stderr);
  assert.equal(result.status, status, result.stdout + result.stderr);
  const report = JSON.parse(readFileSync(output + '.diagnosis.json', 'utf8'));
  if (status === 0) {
    const code = readFileSync(output, 'utf8');
    assert.match(code, /Text\("Before"\)/); assert.match(code, /Text\("After"\)/);
    assert.doesNotMatch(code, /verticalScroll|rememberScrollState|Omitted constraints/);
    assert.ok(report.degradations.some(d => d.action === 'omitted_private_modifier'));
  } else {
    assert.equal(existsSync(output), false);
    assert.match(report.blockingFailure.message, /verticalScroll/);
  }
}
console.log(JSON.stringify({ok: true, root}));
