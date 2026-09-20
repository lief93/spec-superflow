import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, writeFileSync, existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../../..');
const work = mkdtempSync(join(tmpdir(), 'kotlin-ets-clickable-text-'));
const cpFile = join(work, 'classpath.txt');
writeFileSync(cpFile, JSON.parse(readFileSync('/tmp/kotlin-official-frontend-probe-06/classpath.json', 'utf8')).filter(existsSync).join('\n'));
console.log(`Evidence: ${work}`);
function compile(entry, status = 0) {
  const output = join(work, `${entry}.ets`);
  const args = [join(root, 'kotlin-ets'), '--entry', `clickabletext.${entry}`, '--classpath-file', cpFile,
    '--out', output, join(here, 'Page.kt')];
  const result = spawnSync('bash', args, { encoding: 'utf8', timeout: 600000,
    env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' } });
  writeFileSync(join(work, `${entry}.json`), JSON.stringify({ args, ...result }, null, 2));
  assert.equal(result.status, status, result.stdout + result.stderr);
  assert.equal(existsSync(output), status === 0);
  return status === 0 ? readFileSync(output, 'utf8') : result.stdout + result.stderr;
}
const page = compile('Page');
assert.match(page, /class EtsSpanStyle/);
assert.match(page, /class EtsAnnotatedString/);
assert.match(page, /class EtsAnnotatedStringBuilder/);
assert.match(page, /function __etsAnnotatedGetStringAnnotations/);
assert.match(page, /function __etsListFirstOrNull/);
assert.match(page, /Span\(/);
assert.match(page, /ForEach\(/);
assert.match(page, /Don't have an account\?/);
assert.match(page, /Sign Up/);
assert.doesNotMatch(page, /getStringAnnotations\("tag"/);
assert.match(compile('UnsupportedTag', 2), /Tagged getStringAnnotations is not mapped/);
console.log('PASS bounded ClickableText Span+ForEach, annotated builder, tagged query rejected');
