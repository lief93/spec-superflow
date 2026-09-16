import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {existsSync, mkdtempSync, readFileSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
const launcher = fileURLToPath(new URL('../../../kotlin-ets', import.meta.url));
const source = fileURLToPath(new URL('./Page.kt', import.meta.url));
const root = mkdtempSync(join(tmpdir(), 'kotlin-ets-static-animation-'));
assert.ok(process.argv[2], 'Pass real Compose classpath.txt');
function run(name, entry, extra = []) {
  const output = join(root, name + '.ets');
  const result = spawnSync('bash', [launcher, '--entry', 'staticanimation.' + entry,
    '--classpath-file', process.argv[2], '--out', output, ...extra, source], {
    encoding: 'utf8', maxBuffer: 20 * 1024 * 1024,
    env: {...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC'},
  });
  writeFileSync(join(root, name + '.log'), result.stdout + result.stderr);
  assert.ok(existsSync(output + '.diagnosis.json'), result.stdout + result.stderr);
  return {result, output, report: JSON.parse(readFileSync(output + '.diagnosis.json', 'utf8'))};
}
const page = run('page', 'Page');
assert.equal(page.result.status, 0, page.result.stdout + page.result.stderr);
assert.equal(page.report.status, 'generated_with_degradations');
const actions = page.report.degradations.map(d => d.action);
assert.ok(actions.includes('omitted_animation_effect'));
assert.ok(actions.includes('static_animation_value'));
assert.ok(actions.includes('omitted_modifier'));
const code = readFileSync(page.output, 'utf8');
assert.match(code, /Text\("Before"\)/);
assert.match(code, /Text\("After"\)/);
assert.doesNotMatch(code, /animateTo|LocalDensity|translationY|LaunchedEffect/);
const initial = run('initial', 'InitialValue');
assert.equal(initial.result.status, 0, initial.result.stdout + initial.result.stderr);
assert.match(readFileSync(initial.output, 'utf8'), /new EtsStaticAnimation\(0\.5\)/);
const strict = run('strict', 'Page', ['--unsupported-policy', 'error']);
assert.equal(strict.result.status, 2);
assert.equal(strict.report.degradationCount, 0);
const required = run('required', 'RequiredValue');
assert.equal(required.result.status, 2);
assert.match(required.report.blockingFailure.message, /velocity/);
const mixed = run('mixed', 'MixedLoop');
assert.equal(mixed.result.status, 0, mixed.result.stdout + mixed.result.stderr);
assert.match(readFileSync(mixed.output, 'utf8'), /Text\("Retained"\)/);
console.log(JSON.stringify({ok: true, root, page: page.output, initial: initial.output}));
