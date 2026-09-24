import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {mkdtempSync, readFileSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
const launcher = fileURLToPath(new URL('../../../kotlin-ets', import.meta.url));
const source = fileURLToPath(new URL('./Page.kt', import.meta.url));
const root = mkdtempSync(join(tmpdir(), 'kotlin-ets-modifier-named-'));
const output = join(root, 'Page.ets');
assert.ok(process.argv[2], 'Pass real Compose classpath.txt');
const result = spawnSync('bash', [launcher, '--entry', 'modifiernamed.Page',
  '--classpath-file', process.argv[2], '--out', output, source], {
  encoding: 'utf8', maxBuffer: 20 * 1024 * 1024,
  env: {...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC'},
});
writeFileSync(output + '.log', result.stdout + result.stderr);
assert.equal(result.status, 0, result.stdout + result.stderr);
const report = JSON.parse(readFileSync(output + '.diagnosis.json', 'utf8'));
assert.equal(report.degradationCount, 0);
const code = readFileSync(output, 'utf8');
assert.match(code, /\.width\([\s\S]*?circleSize[\s\S]*?\)\.height\(/);
assert.match(code, /\.height\([\s\S]*?circleSize[\s\S]*?\)\.backgroundColor\(/);
assert.match(code, /\.backgroundColor\([\s\S]*?circleColor[\s\S]*?\)\.borderRadius/);
assert.match(code, /\.borderRadius\("50%"\)/);
assert.match(code, /\.backgroundColor\([\s\S]*?\.colorScheme\.primary[\s\S]*?\)\.padding\(/);
const negative = join(root, 'Effectful.ets');
const failed = spawnSync('bash', [launcher, '--entry', 'modifiernamed.Effectful',
  '--classpath-file', process.argv[2], '--out', negative, source], {
  encoding: 'utf8', maxBuffer: 20 * 1024 * 1024,
  env: {...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC'},
});
writeFileSync(negative + '.log', failed.stdout + failed.stderr);
assert.equal(failed.status, 2);
assert.match(JSON.parse(readFileSync(negative + '.diagnosis.json', 'utf8')).blockingFailure.message,
  /stable values to preserve evaluation order/);
console.log(JSON.stringify({ok: true, root, page: output}));
