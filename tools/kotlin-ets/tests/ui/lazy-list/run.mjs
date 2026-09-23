import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, writeFileSync, existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../../..');
const work = mkdtempSync(join(tmpdir(), 'kotlin-ets-lazy-list-'));
const cpFile = join(work, 'classpath.txt');
writeFileSync(cpFile, JSON.parse(readFileSync('/tmp/kotlin-official-frontend-probe-06/classpath.json', 'utf8')).filter(existsSync).join('\n'));
console.log(`Evidence: ${work}`);
function compile(entry, status = 0) {
  const output = join(work, `${entry}.ets`);
  const args = [join(root, 'kotlin-ets'), '--entry', `lazylist.${entry}`, '--classpath-file', cpFile,
    '--out', output, join(here, 'Page.kt'), join(here, 'Grid.kt')];
  const result = spawnSync('bash', args, { encoding: 'utf8', timeout: 600000,
    env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' } });
  writeFileSync(join(work, `${entry}.json`), JSON.stringify({ args, ...result }, null, 2));
  assert.equal(result.status, status, result.stdout + result.stderr);
  assert.equal(existsSync(output), status === 0);
  return status === 0 ? readFileSync(output, 'utf8') : result.stdout + result.stderr;
}
const page = compile('Page');
assert.match(page, /Scroll\(\)/);
assert.match(page, /ForEach\(/);
assert.match(page, /Text\("Header"\)/);
assert.match(page, /Text\(label\)/);
assert.match(page, /\.scrollable\(ScrollDirection.Vertical\)/);
assert.doesNotMatch(page, /firstVisibleItemIndex/);
assert.match(compile('DefaultState'), /Text\("Only"\)/);
assert.match(compile('Disabled'), /\.enableScrollInteraction\(false\)/);
assert.match(compile('Observed', 2), /LazyListState|observed list state/i);
assert.match(compile('Nonzero', 2), /zero initialFirstVisibleItemIndex/);
assert.match(compile('Indexed', 2), /ignores the source index/);
assert.match(compile('Items', 2), /Unsupported LazyColumn DSL/);
const fixed = compile('FixedGrid');
assert.match(fixed, /Grid\(\)/);
assert.match(fixed, /\.columnsTemplate\("1fr 1fr"\)/);
assert.match(fixed, /GridItem\(\)/);
assert.match(fixed, /ForEach\(/);
assert.match(fixed, /return label;/);
const adaptive = compile('AdaptiveGrid');
assert.match(adaptive, /\.cellLength\(150(?:\.0)?\)/);
assert.match(adaptive, /\.minCount\(1\)/);
assert.match(adaptive, /\.padding\(__etsUniformPadding\(4(?:\.0)?\)\)/);
assert.match(adaptive, /\.enableScrollInteraction\(false\)/);
assert.match(adaptive, /\.toString\(\)/);
assert.match(compile('UnsupportedGridArrangement', 2), /Unsupported .*LazyVerticalGrid argument: verticalArrangement/);
console.log('PASS native LazyColumn and LazyVerticalGrid fixed/adaptive tracks, GridItem wrapping, keys, padding and rejection boundaries');
