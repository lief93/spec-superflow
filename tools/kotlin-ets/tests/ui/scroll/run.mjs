import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, writeFileSync, existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../../..');
const work = mkdtempSync(join(tmpdir(), 'kotlin-ets-scroll-'));
const cpFile = join(work, 'classpath.txt');
writeFileSync(cpFile, JSON.parse(readFileSync('/tmp/kotlin-official-frontend-probe-06/classpath.json', 'utf8')).filter(existsSync).join('\n'));
console.log(`Evidence: ${work}`);
function compile(entry, status = 0) {
  const output = join(work, `${entry}.ets`);
  const args = [join(root, 'kotlin-ets'), '--entry', `scroll.${entry}`, '--classpath-file', cpFile,
    '--out', output, join(here, 'Page.kt')];
  const result = spawnSync('bash', args, { encoding: 'utf8', timeout: 600000,
    env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' } });
  writeFileSync(join(work, `${entry}.json`), JSON.stringify({ args, ...result }, null, 2));
  assert.equal(result.status, status, result.stdout + result.stderr);
  assert.equal(existsSync(output), status === 0);
  return status === 0 ? readFileSync(output, 'utf8') : result.stdout + result.stderr;
}
const page = compile('Page');
assert.match(page, /if \(enabled\)/);
assert.match(page, /Scroll\(\)/);
assert.match(page, /\.scrollable\(ScrollDirection.Vertical\)/);
assert.match(page, /\.scrollable\(ScrollDirection.Horizontal\)/);
assert.match(page, /\.scrollBar\(BarState.Off\)/);
assert.match(page, /Text\("Last"\)/);
assert.match(page, /Row\(\) \{[\s\S]*?Text\("Right"\)[\s\S]*?\.scrollable\(ScrollDirection\.Horizontal\)[\s\S]*?\.width\(120(?:\.0)?\)/);
assert.match(compile('Disabled'), /\.enableScrollInteraction\(false\)/);
assert.match(compile('Nonzero', 2), /zero initial offset/);
const observed = compile('Observed');
assert.match(observed, /@State private state_offset: number = 0/);
assert.match(observed, /Text\("" \+ this\.state_offset\)/);
assert.match(observed, /this\.state_offset = yOffset/);
assert.match(compile('Reverse', 2), /reverseScrolling/);
console.log('PASS native scroll, runtime branches, disabled interaction, unsupported state diagnostics');
