import assert from 'node:assert/strict';
import { existsSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const here = dirname(fileURLToPath(import.meta.url));
const work = mkdtempSync(join(tmpdir(), 'kotlin-ets-diagnostic-files-'));
const probe = process.env.KOTLIN_ETS_PROBE ?? '/tmp/kotlin-official-frontend-probe-06';
const classpath = join(work, 'classpath.txt');
writeFileSync(classpath, JSON.parse(readFileSync(join(probe, 'classpath.json'), 'utf8')).join('\n'));
const page = join(here, 'Page.kt');
const source = readFileSync(page, 'utf8');
console.log(`Evidence: ${work}`);
{
  const entry = 'RequiredPage';
  const output = join(work, `${entry}.ets`);
  const args = [resolve(here, '../../../kotlin-ets'), '--entry', `diagnosticfiles.${entry}`,
    '--classpath-file', classpath, '--out', output, page, join(here, 'Label.kt')];
  const result = spawnSync('bash', args, { encoding: 'utf8', timeout: 600000,
    env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' } });
  writeFileSync(join(work, `${entry}.json`), JSON.stringify({ args, ...result }, null, 2));
  assert.equal(result.status, 0, result.stdout + result.stderr);
  const target = readFileSync(output, 'utf8');
  assert.ok(target.includes('  @Require @Prop state: number;'));
  assert.ok(target.includes('  @Require @Prop onOpen: (() => void);'));
  assert.ok(target.includes('      this.RequiredPage(this.state, this.onOpen)'));
  assert.doesNotMatch(target, /@Require @Prop onOpen: \(\(\) => void\) =|= \(\)\s*=>\s*\{\s*\}/);
}
for (const [entry, token, message] of [
  ['DefaultPage', 'getProperty("title")', /java.lang.System|External call/],
]) {
  const output = join(work, `${entry}.ets`);
  const args = [resolve(here, '../../../kotlin-ets'), '--entry', `diagnosticfiles.${entry}`,
    '--classpath-file', classpath, '--out', output, page, join(here, 'Label.kt')];
  const result = spawnSync('bash', args, { encoding: 'utf8', timeout: 600000,
    env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' } });
  writeFileSync(join(work, `${entry}.json`), JSON.stringify({ args, ...result }, null, 2));
  assert.equal(result.status, 2, result.stdout + result.stderr);
  const report = JSON.parse(result.stdout.trim().split('\n').at(-1));
  assert.match(report.message, message);
  assert.equal(resolve(report.source.file), page);
  assert.equal(source.slice(report.source.start, report.source.end), token);
  assert.equal(report.source.line, source.slice(0, report.source.start).split('\n').length);
  assert.equal(existsSync(output), false);
}
console.log('PASS required entry props and cross-file expression diagnostics');
