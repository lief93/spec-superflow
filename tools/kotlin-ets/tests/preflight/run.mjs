import assert from 'node:assert/strict';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../..');
mkdirSync(join(here, '.work'), { recursive: true });
const work = mkdtempSync(join(here, '.work/run-'));
console.log(`Evidence: ${work}`);
function run(label, command, args, expected = 0) {
  const result = spawnSync(command, args, { encoding: 'utf8', timeout: 600000, maxBuffer: 16 * 1024 * 1024,
    env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' } });
  writeFileSync(join(work, `${label}.json`), JSON.stringify({ command, args, status: result.status,
    stdout: result.stdout, stderr: result.stderr }, null, 2));
  if (result.error) throw result.error;
  assert.equal(result.status, expected, result.stdout + result.stderr);
  return result;
}
const cli = join(root, 'kotlin-ets');
const compiler = join(root, 'tests/stdlib/compiler.sh');
const compilerClasspath = run('classpath', 'bash', [compiler, '--classpath']).stdout.trim();
function compile(label, modeArgs, source, expected = 0, classpath = compilerClasspath) {
  const output = join(work, `${label}.ets`);
  const preflight = join(work, `${label}.preflight.json`);
  const result = run(label, 'bash', [cli, ...modeArgs, '--preflight-out', preflight,
    '--classpath', classpath, '--out', output, source], expected);
  assert.ok(existsSync(preflight), 'preflight must be published before target generation');
  return { result, output, report: JSON.parse(readFileSync(preflight, 'utf8')) };
}
function entry(report, symbol) {
  return report.calls.find(call => call.resolvedSymbol.startsWith(symbol));
}

const positive = compile('core-profile', ['--mode', 'language'], join(here, 'CoreProfile.kt'));
assert.equal(JSON.parse(positive.result.stdout).ok, true);
assert.ok(existsSync(positive.output));
assert.equal(positive.report.schemaVersion, 2);
assert.deepEqual(new Set(positive.report.calls.map(call => call.category)), new Set(['language_semantics', 'standard_library']));
const local = entry(positive.report, 'preflightfixture.withSourceDefault(');
assert.equal(local.expectedTargetType, 'string');
assert.deepEqual(local.argumentResolutions, [{ parameter: 'value', resolution: 'source_default' }]);
assert.equal(local.source.line, 7);
assert.equal(local.source.column, 29);
assert.ok(local.source.endColumn > local.source.column);
assert.equal(entry(positive.report, 'kotlin.Int.plus(').expectedTargetType, 'number');
for (const call of positive.report.calls) {
  assert.equal(call.finalRecognizedNode.source.line, call.source.line);
  assert.equal(call.firstUnsupportedNode, null);
  assert.ok(call.responsibleModule.startsWith('tools/kotlin-ets/src/'));
}

const platform = compile('platform', ['--mode', 'language'], join(here, 'Platform.kt'), 2);
const platformFailure = JSON.parse(platform.result.stdout);
assert.equal(platformFailure.code, 'UNSUPPORTED');
assert.equal(platformFailure.source.line, 3);
assert.equal(entry(platform.report, 'java.lang.System.gc(').category, 'project_dependencies');
assert.match(platform.report.firstUnsupportedNode.message, /Unsupported external call/);
assert.equal(entry(platform.report, 'java.lang.System.gc(').firstUnsupportedNode.source.line, 3);
assert.equal(existsSync(platform.output), false);

const dependencyJar = join(work, 'dependency.jar');
run('dependency-compile', 'bash', [compiler, join(here, 'Dependency.kt'), '-d', dependencyJar]);
const dependency = compile('dependency', ['--mode', 'language'], join(here, 'DependencyConsumer.kt'), 2,
  `${compilerClasspath}:${dependencyJar}`);
assert.equal(JSON.parse(dependency.result.stdout).code, 'UNSUPPORTED');
assert.equal(entry(dependency.report, 'projectdependency.dependencyValue(').category, 'project_dependencies');
assert.equal(existsSync(dependency.output), false);

const probe = process.env.KOTLIN_ETS_PROBE ?? '/tmp/kotlin-official-frontend-probe-06';
const composeClasspath = JSON.parse(readFileSync(join(probe, 'classpath.json'), 'utf8')).join(':');
const compose = compile('compose', ['--mode', 'page', '--unsupported-policy', 'error',
  '--entry', 'composablevalues.ComposableValues'], join(root, 'tests/ui/ComposableValues.kt'), 0, composeClasspath);
assert.equal(entry(compose.report, 'androidx.compose.foundation.layout.Column(').category, 'neutral_compose_widget');
assert.equal(entry(compose.report, 'androidx.compose.material3.Text(').category, 'neutral_compose_widget');

const coverage = compile('coverage', ['--mode', 'page', '--unsupported-policy', 'error',
  '--entry', 'preflightfixture.CoveragePage'], join(here, 'Coverage.kt'), 2, composeClasspath);
assert.equal(JSON.parse(coverage.result.stdout).code, 'UNSUPPORTED');
assert.deepEqual(new Set(coverage.report.calls.map(call => call.category)),
  new Set(['neutral_compose_widget', 'modifier', 'resources']));
assert.equal(entry(coverage.report, 'androidx.compose.foundation.layout.size(').category, 'modifier');
assert.equal(entry(coverage.report, 'androidx.compose.ui.res.stringResource(').category, 'resources');
assert.equal(coverage.report.coverage.resources.unsupported, 1);
assert.equal(coverage.report.coverage.resources.percentage, 0);
assert.match(coverage.report.firstUnsupportedNode.message, /Dynamic stringResource ID/);
assert.equal(coverage.report.firstUnsupportedNode.kind, 'unsupported_expression');

const empty = compile('empty-ui', ['--mode', 'page', '--unsupported-policy', 'error',
  '--entry', 'preflightfixture.EmptyPage'], join(here, 'EmptyUi.kt'), 2, composeClasspath);
const emptyFailure = JSON.parse(empty.result.stdout);
assert.equal(emptyFailure.code, 'UNSUPPORTED');
assert.match(emptyFailure.message, /Empty UI builder requires an explicit degradation/);
assert.equal(emptyFailure.source.line, 5);
assert.equal(existsSync(empty.output), false);

assert.deepEqual(new Set([
  ...positive.report.calls, ...platform.report.calls, ...dependency.report.calls, ...compose.report.calls,
  ...coverage.report.calls,
].map(call => call.category)), new Set(['language_semantics', 'standard_library', 'neutral_compose_widget',
  'modifier', 'resources', 'project_dependencies']));
console.log('PASS Core Profile: six categories, coverage ownership, recognized/gap nodes and 1-based locations');
console.log('PASS no silent fallback: source defaults recorded; empty UI rejected; unsupported calls publish no target');
