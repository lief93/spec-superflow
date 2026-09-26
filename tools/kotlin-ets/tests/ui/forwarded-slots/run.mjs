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
for (const name of ['Frame', 'Relay', 'Outer']) assert.match(ets,
  new RegExp(`${name}\\(__etsMaterialContext: EtsMaterialContext, content: WrappedBuilder<\\[EtsMaterialContext\\]>`));
assert.match(ets, /OptionalFrame\(__etsMaterialContext: EtsMaterialContext, content: WrappedBuilder<\[EtsMaterialContext\]> \| null/);
assert.match(ets, /ParameterizedFrame\(__etsMaterialContext: EtsMaterialContext, content: WrappedBuilder<\[EtsMaterialContext, string\]>/);
assert.match(ets, /Frame\(__etsMaterialContext, content\)/);
assert.match(ets, /Relay\(__etsMaterialContext, content\)/);
for (const label of ['Forwarded label', 'Optional label', 'Body restored']) {
  assert.match(ets, new RegExp(`Text\\("${label}"\\)`));
}
assert.match(ets, /content\.builder\(new EtsMaterialContext\(/);
assert.match(ets, /content\.builder\(__etsMaterialContext, "Parameterized label"\)/);
assert.match(ets, /Page_ParameterizedFrame_content\(__etsMaterialContext: EtsMaterialContext, label: string\)/);
console.log('PASS multi-hop source slots preserve typed builder boundaries');
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
assert.match(externalEts, /Column\(\)/);
assert.match(externalEts, /content\.builder\(\)/);
console.log('PASS forwarded external adapter content remains in the generated UI');
