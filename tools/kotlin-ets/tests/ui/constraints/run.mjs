import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, writeFileSync, existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../../..');
const work = mkdtempSync(join(tmpdir(), 'kotlin-ets-constraints-'));
const cpFile = join(work, 'classpath.txt');
writeFileSync(cpFile, JSON.parse(readFileSync('/tmp/kotlin-official-frontend-probe-06/classpath.json', 'utf8')).filter(existsSync).join('\n'));
console.log(`Evidence: ${work}`);
for (const [entry, status] of [['Page', 0], ['Propagate', 2]]) {
  const output = join(work, `${entry}.ets`);
  const args = [join(root, 'kotlin-ets'), '--entry', `constraints.${entry}`, '--classpath-file', cpFile,
    '--out', output, join(here, 'Page.kt')];
  const result = spawnSync('bash', args, { encoding: 'utf8', timeout: 600000,
    env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' } });
  writeFileSync(join(work, `${entry}.json`), JSON.stringify({ args, ...result }, null, 2));
  assert.equal(result.status, status, result.stdout + result.stderr);
  assert.equal(existsSync(output), status === 0);
  if (status) assert.match(result.stdout, /propagateMinConstraints/);
  else {
    const code = readFileSync(output, 'utf8');
    assert.match(code, /EtsComposeBoxWithConstraints\(\{ content: new WrappedBuilder/);
    assert.match(code, /BoxWithConstraintsContent_[^(]+\([^)]*bounds: Binding<__etsBoxConstraints>/);
    assert.match(code, /@State private nested: string = "Nested"/);
    assert.match(code, /this\.nested = "Changed"/);
    assert.match(code, /bounds.value.maxWidth/);
    assert.match(code, /fixedWidth: true, fixedHeight: true/);
    assert.match(code, /Text\("Wide"\)/);
    assert.match(code, /Text\("Narrow"\)/);
    const report = JSON.parse(readFileSync(output + '.diagnosis.json', 'utf8'));
    assert.equal(JSON.stringify(report).includes('omitted_ui_call'), false);
  }
}
console.log('PASS typed parent constraints, captured content, runtime size branches, unsupported propagation');
