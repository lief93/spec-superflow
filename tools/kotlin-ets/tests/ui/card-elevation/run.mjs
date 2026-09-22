import assert from 'node:assert/strict';
import { existsSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../../..');
const work = mkdtempSync(join(tmpdir(), 'kotlin-ets-card-elevation-'));
const probe = process.env.KOTLIN_ETS_PROBE ?? '/tmp/kotlin-official-frontend-probe-06';
const cp = JSON.parse(readFileSync(join(probe, 'classpath.json'), 'utf8')).filter(existsSync);
const cpFile = join(work, 'classpath.txt');
writeFileSync(cpFile, cp.join('\n'));
console.log(`Evidence: ${work}`);

function compile(label, entry, source, expectedStatus = 0) {
  const output = join(work, `${label}.ets`);
  const args = [join(root, 'kotlin-ets'), '--entry', entry, '--classpath-file', cpFile,
    '--out', output, join(here, source)];
  const result = spawnSync('bash', args, { encoding: 'utf8', timeout: 600000,
    env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' } });
  writeFileSync(join(work, `${label}.json`), JSON.stringify({ args, ...result }, null, 2));
  assert.equal(result.status, expectedStatus, result.stdout + result.stderr);
  assert.equal(existsSync(output), expectedStatus === 0, `${label} partial ETS`);
  if (expectedStatus === 0) return readFileSync(output, 'utf8');
  const report = JSON.parse(result.stdout.trim().split('\n').at(-1));
  assert.equal(report.code, 'UNSUPPORTED');
  assert.ok(report.source.start >= 0 && report.source.end > report.source.start);
  return result.stdout + result.stderr;
}

const code = compile('page', 'cardelevation.Page', 'Page.kt');
assert.match(code, /export class EtsCardElevation/);
assert.match(code, /new EtsCardElevation\(8(?:\.0)?, 0(?:\.0)?, 0(?:\.0)?, 1(?:\.0)?, 6(?:\.0)?, 0(?:\.0)?\)/);
assert.match(code, /\.shadow\(\{ radius: vp2px\(__etsGet_Raised\(\)\.defaultElevation\) \}\)/);
assert.match(code, /column: true, fixedWidth: true, fixedHeight: true/);
assert.match(code, /\.borderRadius\(\{ topLeft: 4(?:\.0)?, topRight: 4(?:\.0)?, bottomRight: 4(?:\.0)?, bottomLeft: 4(?:\.0)? \}\)\.shadow/);
assert.equal(code.split('.shadow(').length - 1, 1, 'zero elevation must not fabricate a shadow');
assert.match(code, /if \(this\.column\) \{\n\s+Column\(\)/);

assert.match(compile('dynamic', 'cardelevation.unsupported.DynamicPage', 'Unsupported.kt', 2),
  /Card elevation requires a static numeric Dp/);
assert.match(compile('runtime', 'cardelevation.unsupported.RuntimePage', 'Unsupported.kt', 2),
  /Runtime CardElevation selection is unsupported/);
assert.match(compile('interactive', 'cardelevation.unsupported.InteractivePage', 'Unsupported.kt', 2),
  /Interactive Card elevation states cannot be represented/);

console.log('PASS typed CardElevation, static Harmony Card shadow, Column content and explicit dynamic/stateful rejection');
