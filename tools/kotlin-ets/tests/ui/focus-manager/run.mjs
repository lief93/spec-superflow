import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, writeFileSync, existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const here = dirname(fileURLToPath(import.meta.url)), root = resolve(here, '../../..');
const work = mkdtempSync(join(tmpdir(), 'kotlin-ets-focus-manager-'));
console.log(`Evidence: ${work}`);
const cp = JSON.parse(readFileSync('/tmp/kotlin-official-frontend-probe-06/classpath.json', 'utf8')).filter(existsSync);
writeFileSync(join(work, 'classpath.txt'), cp.join('\n'));
function compile(entry, status) {
  const out = join(work, entry + '.ets');
  const args = [join(root, 'kotlin-ets'), '--mode', 'page', '--entry', 'focusmanager.' + entry,
    '--classpath-file', join(work, 'classpath.txt'), '--out', out, join(here, 'Page.kt')];
  const result = spawnSync('bash', args, { encoding: 'utf8', timeout: 600000,
    env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' } });
  writeFileSync(out + '.json', JSON.stringify({ args, ...result }, null, 2));
  assert.equal(result.status, status, result.stdout + result.stderr);
  assert.equal(existsSync(out), status === 0);
  return status === 0 ? readFileSync(out, 'utf8') : result.stdout;
}
const page = compile('Page', 0);
writeFileSync(join(work, 'Page.ets'), page);
const check = spawnSync(process.execPath, [join(here, 'check.mjs'), join(work, 'Page.ets')],
  { encoding: 'utf8', timeout: 60000 });
writeFileSync(join(work, 'check.json'), JSON.stringify(check, null, 2));
assert.equal(check.status, 0, check.stdout + check.stderr);
const move = JSON.parse(compile('Unsupported', 2).trim().split('\n').at(-1));
assert.match(move.message, /Unsupported external call: androidx\.compose\.ui\.focus\.FocusManager\.moveFocus/);
assert.equal(resolve(move.source.file), join(here, 'Page.kt'));
const soft = JSON.parse(compile('SoftClear', 2).trim().split('\n').at(-1));
assert.match(soft.message, /FocusManager\.clearFocus only supports the default force=true argument/);
assert.equal(resolve(soft.source.file), join(here, 'Page.kt'));
console.log('PASS LocalFocusManager identity, native clearFocus and source-linked rejection');
