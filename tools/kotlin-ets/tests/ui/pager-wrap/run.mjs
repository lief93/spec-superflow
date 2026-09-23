import assert from 'node:assert/strict';
import { existsSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../../..');
const work = mkdtempSync(join(tmpdir(), 'kotlin-ets-pager-wrap-'));
const classpath = JSON.parse(readFileSync('/tmp/kotlin-official-frontend-probe-06/classpath.json')).filter(existsSync);
const classpathFile = join(work, 'classpath.txt');
const output = join(work, 'Page.ets');
writeFileSync(classpathFile, classpath.join('\n') + '\n');
console.log('Evidence: ' + work);

const result = spawnSync('bash', [join(root, 'kotlin-ets'), '--mode', 'page', '--unsupported-policy', 'error',
  '--entry', 'pagerwrap.Page', '--classpath-file', classpathFile, '--out', output, join(here, 'Page.kt')], {
  encoding: 'utf8', timeout: 600000,
  env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' },
});
writeFileSync(join(work, 'command.json'), JSON.stringify({ status: result.status, stdout: result.stdout,
  stderr: result.stderr }, null, 2));
assert.equal(result.status, 0, result.stdout + result.stderr);

const code = readFileSync(output, 'utf8');
const swiper = code.indexOf('Swiper(');
const after = code.indexOf('Text("After pager")');
assert.ok(swiper >= 0 && after > swiper, 'fixture must retain the Pager followed by its sibling');
const pagerCode = code.slice(swiper, after);
assert.match(pagerCode, /Text\("" \+ "Page " \+ page\)/, 'Pager page content is retained');
assert.doesNotMatch(pagerCode, /Column\(\)[^\n]*\.height\("100%"\)/,
  'fillMaxHeight is a no-op for page content measured under wrapContentHeight');
assert.equal(JSON.parse(result.stdout.trim().split('\n').at(-1)).degradationCount, 0);
console.log('PASS Pager wrapContentHeight propagates an unbounded height to page content');
