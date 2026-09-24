import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, writeFileSync, existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../../..');
const work = mkdtempSync(join(tmpdir(), 'kotlin-ets-pointer-input-'));
const cpFile = join(work, 'classpath.txt');
writeFileSync(cpFile, JSON.parse(readFileSync('/tmp/kotlin-official-frontend-probe-06/classpath.json', 'utf8')).filter(existsSync).join('\n'));
console.log(`Evidence: ${work}`);
function compile(entry, status = 0) {
  const output = join(work, `${entry}.ets`);
  const args = [join(root, 'kotlin-ets'), '--entry', `pointerinput.${entry}`, '--classpath-file', cpFile,
    '--out', output, join(here, 'Page.kt')];
  const result = spawnSync('bash', args, { encoding: 'utf8', timeout: 600000,
    env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' } });
  writeFileSync(join(work, `${entry}.json`), JSON.stringify({ args, ...result }, null, 2));
  assert.equal(result.status, status, result.stdout + result.stderr);
  assert.equal(existsSync(output), status === 0);
  return status === 0 ? readFileSync(output, 'utf8') : result.stdout + result.stderr;
}
assert.match(compile('Page'), /\.hitTestBehavior\(HitTestMode.Default\)/);
const tap = compile('Tap');
assert.match(tap, /\.hitTestBehavior\(HitTestMode.Default\)/);
assert.match(tap, /\.onClick\(\(\): void => \{/);
assert.match(tap, /this\.taps = this\.taps \+ 1/);
assert.match(compile('Nonempty', 2), /raw pointer processing is not supported/);
assert.match(compile('EvaluatedKey', 2), /pointerInput.*effect-free keys/);
console.log('PASS empty input hit-test mapping and explicit nonempty/key diagnostics');
