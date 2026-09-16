import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {existsSync, mkdtempSync, readFileSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';

const launcher = fileURLToPath(new URL('../../../kotlin-ets', import.meta.url));
const source = fileURLToPath(new URL('./Page.kt', import.meta.url));
const classpath = process.argv[2];
assert.ok(classpath, 'usage: node check.mjs <real Compose classpath.txt>');
const root = mkdtempSync(join(tmpdir(), 'kotlin-ets-degradation-'));
function run(name, entry, extra = []) {
  const output = join(root, `${name}.ets`);
  const result = spawnSync('bash', [launcher, '--entry', `degradation.${entry}`,
    '--classpath-file', classpath, '--out', output, ...extra, source], {
    encoding: 'utf8', maxBuffer: 20 * 1024 * 1024,
    env: {...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC'},
  });
  writeFileSync(join(root, `${name}.log`), result.stdout + result.stderr);
  assert.equal(result.error, undefined);
  const events = result.stdout.trim().split('\n').filter(line => line.startsWith('{')).map(JSON.parse);
  console.log(`${name}: exit ${result.status}`);
  return {output, result, event: events.at(-1), report: existsSync(output + '.diagnosis.json')
    ? JSON.parse(readFileSync(output + '.diagnosis.json', 'utf8')) : null};
}
const page = run('page', 'Page');
assert.equal(page.result.status, 0, page.result.stdout + page.result.stderr);
assert.equal(page.event.status, 'generated_with_degradations');
assert.equal(page.event.diagnosis, page.output + '.diagnosis.json');
assert.equal(page.event.degradationCount, 4);
assert.equal(page.report.equivalenceVerified, false);
assert.equal(page.report.blockingFailure, null);
assert.equal(page.report.degradationCount, 4);
assert.deepEqual(page.report.degradations.map(d => d.action), [
  'omitted_display_argument', 'omitted_modifier', 'omitted_ui_call', 'omitted_ui_call',
]);
assert.deepEqual(page.report.degradations.map(d => d.source.line), [17, 17, 18, 19]);
for (const diagnostic of page.report.degradations) {
  assert.equal(diagnostic.source.file, source);
  assert.ok(diagnostic.source.column > 0);
  assert.ok(diagnostic.source.end > diagnostic.source.start);
  assert.match(diagnostic.capability, /^androidx\.compose\./);
  assert.ok(diagnostic.impact.length > 0);
}
const code = readFileSync(page.output, 'utf8');
assert.match(code, /Text\("Before"\)/);
assert.match(code, /Text\("After"\)/);
assert.match(code, /\.width\(160\.0\)\.padding\(8\.0\)/);
assert.doesNotMatch(code, /CircularProgressIndicator|SideEffect|System|getProperty|\.blur\(/);

const strict = run('strict', 'Page', ['--unsupported-policy', 'error']);
assert.equal(strict.result.status, 2);
assert.equal(existsSync(strict.output), false);
assert.equal(strict.report.status, 'blocked');
assert.equal(strict.report.degradationCount, 0);
assert.match(strict.report.blockingFailure.message, /softWrap/);

const required = run('required', 'RequiredValue');
assert.equal(required.result.status, 2);
assert.equal(existsSync(required.output), false);
assert.equal(required.report.status, 'blocked');
assert.equal(required.report.degradationCount, 1);
assert.match(required.report.blockingFailure.message, /SDK_INT/);
assert.equal(required.report.blockingFailure.source.line, 26);

const claimed = run('claimed', 'ClaimedFailure');
assert.equal(claimed.result.status, 2);
assert.equal(existsSync(claimed.output), false);
assert.equal(claimed.report.status, 'blocked');
assert.equal(claimed.report.degradationCount, 0);
assert.match(claimed.report.blockingFailure.message, /onTextLayout/);

const clean = run('clean', 'Clean');
assert.equal(clean.result.status, 0);
assert.equal(clean.report.status, 'generated');
assert.equal(clean.report.degradationCount, 0);

const collision = join(root, 'collision.ets.diagnosis.json');
writeFileSync(collision, '{"user":"owned"}');
const conflict = run('collision', 'Clean');
assert.equal(conflict.result.status, 1);
assert.equal(existsSync(conflict.output), false);
assert.match(conflict.event.message, /Refusing to overwrite existing diagnosis/);
assert.equal(readFileSync(collision, 'utf8'), '{"user":"owned"}');

const language = run('language', 'Clean', ['--mode', 'language', '--unsupported-policy', 'report']);
assert.equal(language.result.status, 1);
assert.match(language.event.message, /Language mode requires/);
assert.equal(language.report, null);
assert.equal(existsSync(language.output), false);
console.log(JSON.stringify({ok: true, root, page: page.output}));
