import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {existsSync, mkdtempSync, readFileSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';

const launcher = fileURLToPath(new URL('../../../kotlin-ets', import.meta.url));
const toolRoot = fileURLToPath(new URL('../../..', import.meta.url));
const source = fileURLToPath(new URL('./Page.kt', import.meta.url));
const valuesSource = fileURLToPath(new URL('./PlatformVersionValues.kt', import.meta.url));
const oracleSource = fileURLToPath(new URL('./JvmOracle.kt', import.meta.url));
const classpath = process.argv[2];
assert.ok(classpath, 'Pass real Compose classpath.txt');
const root = mkdtempSync(join(tmpdir(), 'kotlin-ets-theme-projection-'));
function run(name, entry, extra = []) {
  const output = join(root, name + '.ets');
  const result = spawnSync('bash', [launcher, '--entry', 'themeprojection.' + entry,
    '--classpath-file', classpath, '--out', output, ...extra, valuesSource, source], {
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
const shared = run('SharedValue', 'SharedValue');
assert.equal(shared.result.status, 2, shared.result.stdout + shared.result.stderr);
assert.match(shared.report.blockingFailure.message, /SDK_INT/);
assert.equal(existsSync(shared.output), false);
const guarded = run('RequiredCondition', 'RequiredCondition');
assert.equal(guarded.result.status, 0, guarded.result.stdout + guarded.result.stderr);
assert.deepEqual(guarded.report.degradations.map(d => d.action), ['platform_capability_fallback']);
assert.match(guarded.report.degradations[0].message, /SDK_INT/);
assert.doesNotMatch(readFileSync(guarded.output, 'utf8'), /SDK_INT/);
const below = run('BelowCondition', 'BelowCondition');
assert.equal(below.result.status, 0, below.result.stdout + below.result.stderr);
assert.deepEqual(below.report.degradations.map(d => d.action), ['platform_capability_fallback']);
assert.doesNotMatch(readFileSync(below.output, 'utf8'), /SDK_INT|VERSION_CODES/);
const combined = run('CombinedCondition', 'CombinedCondition');
assert.equal(combined.result.status, 0, combined.result.stdout + combined.result.stderr);
assert.deepEqual(combined.report.degradations.map(d => d.action), ['platform_capability_fallback']);
const combinedCode = readFileSync(combined.output, 'utf8');
assert.equal(combinedCode.split('effectfulCondition()').length - 1, 2,
  'one function declaration and one condition call prove the non-platform effect is evaluated once');
assert.doesNotMatch(combinedCode, /supportsDynamicTheming|SDK_INT|VERSION_CODES/);
const noFallback = run('RequiredNoFallback', 'RequiredNoFallback');
assert.equal(noFallback.result.status, 2, noFallback.result.stdout + noFallback.result.stderr);
assert.match(noFallback.report.blockingFailure.message, /meaningful fallback/);
assert.ok(noFallback.report.blockingFailure.source.line > 0 && noFallback.report.blockingFailure.source.column > 0);
assert.equal(existsSync(noFallback.output), false);
const valueFallback = run('ValueFallback', 'ValueFallback');
assert.equal(valueFallback.result.status, 0, valueFallback.result.stdout + valueFallback.result.stderr);
assert.deepEqual(valueFallback.report.degradations.map(d => d.action), ['platform_capability_fallback']);
assert.match(readFileSync(valueFallback.output, 'utf8'), /return false \? "mapped" : "fallback"/);
const clean = run('clean', 'Clean');
assert.equal(clean.result.status, 0, clean.result.stdout + clean.result.stderr);
assert.equal(clean.report.degradationCount, 0);
assert.doesNotMatch(readFileSync(clean.output, 'utf8'), /__etsCurrentProjectColorScheme/);
const business = run('business', 'BusinessEffect');
assert.equal(business.result.status, 2);
assert.equal(existsSync(business.output), false);
assert.ok(!business.report.degradations.some(d => d.action === 'omitted_theme_effect'));
const dependencies = readFileSync(classpath, 'utf8').split(/\r?\n/).filter(Boolean);
const oracleJar = join(root, 'oracle.jar');
const oracleBuild = spawnSync('bash', [join(toolRoot, 'tests/stdlib/compiler.sh'), '-classpath', dependencies.join(':'),
  valuesSource, oracleSource, '-d', oracleJar], {encoding: 'utf8', timeout: 120000});
assert.equal(oracleBuild.status, 0, oracleBuild.stdout + oracleBuild.stderr);
const oracle = spawnSync('java', ['-cp', [oracleJar, ...dependencies].join(':'), 'themeprojection.JvmOracleKt'],
  {encoding: 'utf8', timeout: 120000});
assert.equal(oracle.status, 0, oracle.stdout + oracle.stderr);
assert.equal(oracle.stdout.trim(), 'fallback');
console.log(JSON.stringify({ok: true, root, page: page.output}));
