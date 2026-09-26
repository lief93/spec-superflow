import assert from 'node:assert/strict';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { materializeProjectImages } from '../../image-resources.mjs';

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
function cachedJar(group, artifact, version) {
  const directory = join(process.env.HOME, '.gradle/caches/modules-2/files-2.1', group, artifact, version);
  for (const hash of readdirSync(directory).sort()) {
    const candidate = join(directory, hash, `${artifact}-${version}.jar`);
    if (existsSync(candidate)) return candidate;
  }
  assert.fail(`Required cached compiler artifact is absent: ${group}:${artifact}:${version}`);
}
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
assert.equal(positive.report.projectCompilerVersion, null);
assert.equal(positive.report.frontendCompilerVersion, '2.1.20');
assert.equal(positive.report.compatibilityDecision, 'direct_source_input');
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
assert.match(entry(platform.report, 'java.lang.System.gc(').firstUnsupportedNode.message, /Unsupported external call/);
assert.equal(entry(platform.report, 'java.lang.System.gc(').firstUnsupportedNode.source.line, 3);
const unsupportedType = entry(platform.report, 'java.lang.System.getProperties(');
assert.equal(unsupportedType.firstUnsupportedNode.kind, 'target_type');
assert.equal(unsupportedType.firstUnsupportedNode.source.line, unsupportedType.source.line);
assert.equal(unsupportedType.firstUnsupportedNode.source.column, unsupportedType.source.column);
assert.equal(platform.report.firstUnsupportedNode.source.line, unsupportedType.source.line);
assert.equal(existsSync(platform.output), false);

const dependencyJar = join(work, 'dependency.jar');
run('dependency-compile', 'bash', [compiler, join(here, 'Dependency.kt'), '-d', dependencyJar]);
const dependency = compile('dependency', ['--mode', 'language'], join(here, 'DependencyConsumer.kt'), 2,
  `${compilerClasspath}:${dependencyJar}`);
assert.equal(JSON.parse(dependency.result.stdout).code, 'UNSUPPORTED');
assert.equal(entry(dependency.report, 'projectdependency.dependencyValue(').category, 'project_dependencies');
assert.equal(existsSync(dependency.output), false);

const newerCompilerClasspath = [
  ['org.jetbrains.kotlin', 'kotlin-compiler-embeddable', '2.3.20'],
  ['org.jetbrains.kotlin', 'kotlin-stdlib', '2.3.20'],
  ['org.jetbrains.kotlin', 'kotlin-script-runtime', '2.3.20'],
  ['org.jetbrains.kotlin', 'kotlin-reflect', '2.3.20'],
  ['org.jetbrains.kotlin', 'kotlin-daemon-embeddable', '2.3.20'],
  ['org.jetbrains.intellij.deps', 'trove4j', '1.0.20200330'],
  ['org.jetbrains.kotlinx', 'kotlinx-coroutines-core-jvm', '1.10.1'],
  ['org.jetbrains', 'annotations', '13.0'],
].map(coordinates => cachedJar(...coordinates)).join(':');
const newerDependencyJar = join(work, 'newer-metadata.jar');
run('newer-metadata-compile', 'java', ['-cp', newerCompilerClasspath,
  'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler', '-no-stdlib', '-no-reflect',
  '-classpath', newerCompilerClasspath, '-d', newerDependencyJar, join(here, 'NewerMetadata.kt')]);
const incompatibleMetadataOutput = join(work, 'incompatible-metadata.ets');
const incompatibleMetadataReport = join(work, 'incompatible-metadata.preflight.json');
const incompatibleMetadata = run('incompatible-metadata', 'bash', [cli, '--mode', 'language',
  '--preflight-out', incompatibleMetadataReport, '--classpath', `${compilerClasspath}:${newerDependencyJar}`,
  '--out', incompatibleMetadataOutput, join(here, 'NewerMetadataConsumer.kt')], 1);
assert.equal(JSON.parse(incompatibleMetadata.stdout).code, 'COMPILATION_REJECTED');
assert.match(incompatibleMetadata.stderr,
  /module was compiled with an incompatible version of Kotlin.*binary version of its metadata is 2\.3\.0, expected version is 2\.1\.0/);
assert.match(incompatibleMetadata.stderr, /NewerMetadataConsumer\.kt:3:49: error: \[UNRESOLVED_REFERENCE\]/);
assert.equal(existsSync(incompatibleMetadataReport), false);
assert.equal(existsSync(incompatibleMetadataOutput), false);

const probe = process.env.KOTLIN_ETS_PROBE ?? '/tmp/kotlin-official-frontend-probe-06';
const composeClasspath = JSON.parse(readFileSync(join(probe, 'classpath.json'), 'utf8')).join(':');
const projectProfileOutput = join(work, 'project-profile-report.json');
const projectProfileResult = run('project-profile', 'bash', [cli, '--mode', 'preflight',
  '--classpath', composeClasspath, '--out', projectProfileOutput, join(here, 'ProjectProfile.kt')]);
const projectProfile = JSON.parse(readFileSync(projectProfileOutput, 'utf8'));
assert.equal(JSON.parse(projectProfileResult.stdout).status, 'profiled');
assert.deepEqual(projectProfile.pageEntries, ['preflightfixture.ProjectProfilePreview']);
assert.ok(projectProfile.calls.length > 0);
assert.ok(projectProfile.calls.some(call => call.resolvedSymbol.startsWith('androidx.compose.material3.Text(')));
assert.ok(projectProfile.calls.some(call => call.resolvedSymbol.startsWith('kotlin.text.uppercase(')));
assert.ok(projectProfile.unsupportedNodes.some(node => node.symbol === 'java.lang.Runnable' && node.kind === 'super_type'));
assert.equal(existsSync(`${projectProfileOutput}.diagnosis.json`), false);

const compose = compile('compose', ['--mode', 'page', '--unsupported-policy', 'error',
  '--entry', 'composablevalues.ComposableValues'], join(root, 'tests/ui/ComposableValues.kt'), 0, composeClasspath);
assert.equal(entry(compose.report, 'androidx.compose.foundation.layout.Column(').category, 'neutral_compose_widget');
assert.equal(entry(compose.report, 'androidx.compose.material3.Text(').category, 'neutral_compose_widget');
assert.ok(compose.report.unsupportedNodes.every(node => node.symbol !== 'androidx.compose.foundation.layout.RowScope'),
  'generated source component slots must reconcile speculative receiver declaration types');
assert.equal((readFileSync(compose.output, 'utf8').match(/\.layoutWeight\(1(?:\.0)?\)/g) ?? []).length, 2,
  'forwarded and direct RowScope content must retain row-layout modifier semantics');

const scroll = compile('generated-scroll-state', ['--mode', 'page', '--unsupported-policy', 'error',
  '--entry', 'widgetscroll.ScrollProfile'], join(root, 'tests/ui/widgets/ScrollProfile.kt'), 0, composeClasspath);
const scrollStates = scroll.report.calls.filter(call =>
  call.resolvedSymbol.startsWith('androidx.compose.foundation.rememberScrollState('));
assert.equal(scrollStates.length, 2);
assert.ok(scrollStates.every(call => call.firstUnsupportedNode === null),
  'validated target IR must reconcile speculative state target-type failures');
assert.equal(scroll.report.coverage.neutral_compose_widget.unsupported, 0);
assert.ok(scroll.report.unsupportedNodes.every(node => node.symbol !== 'androidx.compose.foundation.ScrollState'),
  'validated state fields must reconcile speculative source declaration types');

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

const projectImageRoot = join(work, 'project-image-res');
mkdirSync(join(projectImageRoot, 'drawable'), { recursive: true });
writeFileSync(join(projectImageRoot, 'drawable/selector.xml'), '<selector/>');
const imageBits = JSON.parse(readFileSync(join(root, 'tests/resources/fixtures/bitmaps.json'), 'utf8'));
writeFileSync(join(projectImageRoot, 'drawable/supported.png'), Buffer.from(imageBits.png, 'base64'));
const projectImageSymbols = join(work, 'project-image-R.txt');
writeFileSync(projectImageSymbols,
  'int drawable selector 0x7f040001\nint drawable missing 0x7f040002\nint drawable supported 0x7f040003\n');
const projectImages = materializeProjectImages({ namespace: 'preflightfixture', variant: 'debug',
  resourceRoots: [{ sourceSet: 'main', overlayPriority: 0, path: projectImageRoot }],
  symbolsFile: projectImageSymbols, out: join(work, 'project-images') });
const selector = compile('unsupported-project-image', ['--mode', 'page', '--unsupported-policy', 'error',
  '--entry', 'preflightfixture.UnsupportedProjectImage', '--image-resources', projectImages.properties],
join(here, 'ProjectImageFailures.kt'), 2, composeClasspath);
assert.match(JSON.parse(selector.result.stdout).message, /Unsupported Android image resource.*<selector>/);
assert.equal(selector.report.firstUnsupportedNode.source.line, 17);
assert.equal(existsSync(selector.output), false);
const missingImage = compile('missing-project-image', ['--mode', 'page', '--unsupported-policy', 'error',
  '--entry', 'preflightfixture.MissingProjectImage', '--image-resources', projectImages.properties],
join(here, 'ProjectImageFailures.kt'), 2, composeClasspath);
assert.match(JSON.parse(missingImage.result.stdout).message, /No .*R\.drawable\.missing file exists in collected module resource roots/);
assert.equal(missingImage.report.firstUnsupportedNode.source.line, 22);
assert.equal(existsSync(missingImage.output), false);
const supportedImage = compile('supported-project-image', ['--mode', 'page', '--unsupported-policy', 'error',
  '--entry', 'preflightfixture.SupportedProjectImage', '--image-resources', projectImages.properties],
join(here, 'ProjectImageFailures.kt'), 0, composeClasspath);
assert.equal(JSON.parse(supportedImage.result.stdout).ok, true);
const supportedTarget = readFileSync(supportedImage.output, 'utf8');
assert.match(supportedTarget, /\$r\(["']app\.media\.img_[0-9a-f]{64}["']\)/);
const supportedName = /preflightfixture\.R\.drawable\.supported = ([a-z0-9_]+)/
  .exec(readFileSync(projectImages.properties, 'utf8'))[1];
assert.ok(existsSync(join(`${supportedImage.output}.resources`, 'base/media', `${supportedName}.png`)));
assert.ok(existsSync(join(`${supportedImage.output}.resources`, 'image-resource-origins.json')));

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
for (const call of [positive, platform, dependency, compose, coverage].flatMap(result => result.report.calls)) {
  assert.ok(call.source.line > 0 && call.source.column > 0);
  assert.ok(call.finalRecognizedNode.source.line > 0 && call.finalRecognizedNode.source.column > 0);
  if (call.firstUnsupportedNode)
    assert.ok(call.firstUnsupportedNode.source.line > 0 && call.firstUnsupportedNode.source.column > 0);
}
console.log('PASS Core Profile: six categories, coverage ownership, recognized/gap nodes and 1-based locations');
console.log('PASS project profile: complete raw module scan, Preview discovery and no target generation');
console.log('PASS no silent fallback: source defaults recorded; empty UI rejected; unsupported calls publish no target');
