import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {existsSync, mkdtempSync, readFileSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';

const launcher = fileURLToPath(new URL('../../../kotlin-ets', import.meta.url));
const source = fileURLToPath(new URL('./Page.kt', import.meta.url));
const classpath = process.argv[2];
assert.ok(classpath, 'Pass real Compose classpath.txt');
const root = mkdtempSync(join(tmpdir(), 'kotlin-ets-theme-projection-'));
function run(name, entry, extra = []) {
  const output = join(root, name + '.ets');
  const result = spawnSync('bash', [launcher, '--entry', 'themeprojection.' + entry,
    '--classpath-file', classpath, '--out', output, ...extra, source], {
    encoding: 'utf8', maxBuffer: 20 * 1024 * 1024,
    env: {...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC'},
  });
  writeFileSync(join(root, name + '.log'), result.stdout + result.stderr);
  assert.equal(result.error, undefined);
  assert.ok(existsSync(output + '.diagnosis.json'), result.stdout + result.stderr);
  const report = JSON.parse(readFileSync(output + '.diagnosis.json', 'utf8'));
  return {result, report, output};
}
const page = run('page', 'Page');
assert.equal(page.result.status, 0, page.result.stdout + page.result.stderr);
assert.equal(page.report.status, 'generated_with_degradations');
assert.deepEqual(page.report.degradations.map(d => d.action), ['project_theme_replacement', 'omitted_theme_effect']);
assert.equal(page.report.equivalenceVerified, false);
for (const d of page.report.degradations) {
  assert.equal(d.source.file, source);
  assert.ok(d.source.line > 0 && d.source.column > 0);
}
const code = readFileSync(page.output, 'utf8');
assert.match(code, /__etsCurrentProjectColorScheme\(/);
assert.match(code, /Text\("Preserved content"\)/);
assert.match(code, /Text\("First"\)/);
assert.match(code, /Text\("Next"\)/);
assert.match(code, /\.onClick\(/);
assert.doesNotMatch(code, /SDK_INT|LocalView|androidPalette|statusBarColor/);

const strict = run('strict', 'Page', ['--unsupported-policy', 'error']);
assert.equal(strict.result.status, 2);
assert.equal(strict.report.degradationCount, 0);
assert.match(strict.report.blockingFailure.message, /SDK_INT/);
assert.equal(existsSync(strict.output), false);
for (const entry of ['SharedValue', 'RequiredCondition']) {
  const test = run(entry, entry);
  assert.equal(test.result.status, 2, test.result.stdout + test.result.stderr);
  assert.match(test.report.blockingFailure.message, /SDK_INT/);
  assert.equal(existsSync(test.output), false);
}
const clean = run('clean', 'Clean');
assert.equal(clean.result.status, 0, clean.result.stdout + clean.result.stderr);
assert.equal(clean.report.degradationCount, 0);
assert.doesNotMatch(readFileSync(clean.output, 'utf8'), /__etsCurrentProjectColorScheme/);
console.log(JSON.stringify({ok: true, root, page: page.output}));
