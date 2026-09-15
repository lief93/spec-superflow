import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, writeFileSync, existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
const here = dirname(fileURLToPath(import.meta.url)), root = resolve(here, '../../..');
const work = mkdtempSync(join(tmpdir(), 'kotlin-ets-clip-'));
console.log('Evidence: ' + work);
const cp = join(work, 'classpath.txt');
writeFileSync(cp, JSON.parse(readFileSync('/tmp/kotlin-official-frontend-probe-06/classpath.json')).filter(existsSync).join('\n'));
for (const [entry, status] of [['Page', 0], ['UnsupportedShape', 2]]) {
  const output = join(work, entry + '.ets');
  const args = [join(root, 'kotlin-ets'), '--entry', 'clipping.' + entry, '--classpath-file', cp,
    '--out', output, join(here, 'Page.kt')];
  const result = spawnSync('bash', args, { encoding: 'utf8', timeout: 600000,
    env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' } });
  writeFileSync(join(work, entry + '.json'), JSON.stringify({ args, ...result }, null, 2));
  assert.equal(result.status, status, result.stdout + result.stderr);
  assert.equal(existsSync(output), status === 0);
  if (!status) {
    const source = readFileSync(output, 'utf8');
    assert.match(source, /Tile\(shape: string\)/);
    assert.match(source, /\.borderRadius\(shape\)\.clip\(true\)/);
    assert.match(source, /Tile\("50%"\)/);
    assert.match(source, /Tile\("0vp"\)/);
    assert.match(source, /\.padding\(10(?:\.0)?\)/);
    assert.match(source, /\.backgroundColor\(4278255360\)/);
  }
}
console.log('PASS typed shape parameters, ordered clip output and unsupported shapes');
