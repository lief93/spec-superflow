import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {existsSync, mkdtempSync, readFileSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';

const launcher = fileURLToPath(new URL('../../../kotlin-ets', import.meta.url));
assert.ok(process.argv[2], 'provide a real Compose classpath.txt');
const root = mkdtempSync(join(tmpdir(), 'kotlin-ets-degradation-named-'));
for (const [entry, failure] of [
  ['NamedArguments', /softWrap/], ['ExplicitLocal', /softWrap/], ['UnsupportedNamedArgument', /softWrap/],
  ['RequiredNamedArgument', /softWrap|SDK_INT/], ['UnsupportedType', /AnimatedVisibility/],
  ['ExplicitUnsupportedType', /fadeIn|EnterTransition/],
]) {
  const source = fileURLToPath(new URL(entry.endsWith('Type') ? './TypedArguments.kt' : './NamedArguments.kt', import.meta.url));
  const output = join(root, entry + '.ets');
  const result = spawnSync('bash', [launcher, '--entry', `degradation.${entry}`, '--classpath-file', process.argv[2],
    '--out', output, source], {encoding: 'utf8', maxBuffer: 20 * 1024 * 1024,
    env: {...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC'}});
  writeFileSync(join(root, entry + '.log'), result.stdout + result.stderr);
  assert.equal(result.status, 2, result.stdout + result.stderr);
  const report = JSON.parse(readFileSync(output + '.diagnosis.json', 'utf8'));
  assert.equal(report.status, 'blocked');
  assert.match(report.blockingFailure.message, failure);
  assert.equal(existsSync(output), false);
  assert.equal(report.degradationCount, 0);
  console.log(`PASS ${entry}: unsupported consumer cannot discard its arguments or content`);
}
console.log(JSON.stringify({ok: true, root}));
