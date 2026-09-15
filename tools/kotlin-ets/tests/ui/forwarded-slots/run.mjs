import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const here = dirname(fileURLToPath(import.meta.url));
const work = mkdtempSync(join(tmpdir(), 'kotlin-ets-forwarded-slots-'));
const probe = process.env.KOTLIN_ETS_PROBE ?? '/tmp/kotlin-official-frontend-probe-06';
const classpath = join(work, 'classpath.txt');
writeFileSync(classpath, JSON.parse(readFileSync(join(probe, 'classpath.json'), 'utf8')).join('\n'));
const output = join(work, 'Page.ets');
const args = [resolve(here, '../../../kotlin-ets'), '--entry', 'forwardedslots.Page',
  '--classpath-file', classpath, '--out', output, join(here, 'Page.kt')];
console.log(`Evidence: ${work}`);
const result = spawnSync('bash', args, { encoding: 'utf8', timeout: 600000,
  env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' } });
writeFileSync(join(work, 'result.json'), JSON.stringify({ args, ...result }, null, 2));
assert.equal(result.status, 0, result.stdout + result.stderr);
const ets = readFileSync(output, 'utf8');
for (const name of ['Frame', 'Relay', 'Outer']) assert.match(ets, new RegExp(`${name}\\(content: WrappedBuilder`));
for (const [label, typography] of [['Forwarded label', '14, 20, 500, 0.1'], ['Body restored', '16, 24, 400, 0.5']]) {
  const line = ets.split('\n').find(line => line.includes(`Text("${label}")`));
  assert.ok(line?.includes(`__etsMaterialTypography(${typography})`), line);
}
console.log('PASS multi-hop source slots preserve invocation typography and builder boundaries');
const externalOutput = join(work, 'External.ets');
const externalArgs = [resolve(here, '../../../kotlin-ets'), '--entry', 'demo.adapters.ExternalPage',
  '--classpath-file', classpath, '--out', externalOutput, join(here, 'External.kt')];
const external = spawnSync('bash', externalArgs, { encoding: 'utf8', timeout: 600000,
  env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC',
    KOTLIN_ETS_ADAPTER_DIRS: resolve(here, '../../../examples/adapters') } });
writeFileSync(join(work, 'external.json'), JSON.stringify({ args: externalArgs, ...external }, null, 2));
assert.equal(external.status, 0, external.stdout + external.stderr);
const externalEts = readFileSync(externalOutput, 'utf8');
assert.match(externalEts, /Text\("External frame"\)/);
assert.match(externalEts, /Text\("External content"\)/);
assert.match(externalEts, /__etsMaterialTypography\(16, 24, 400, 0.5\)/);
console.log('PASS forwarded external adapter content remains in the generated UI');
