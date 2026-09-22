import assert from 'node:assert/strict';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../..');
const seed = process.argv[2] && resolve(process.argv[2]);
assert.ok(seed && existsSync(join(seed, '.git')),
  'Usage: node now-in-android.mjs /absolute/path/to/nowinandroid-checkout');

const revision = '5e34fb49c04717265d5351035fcc87f6bba6ed18';
const repository = 'https://github.com/android/nowinandroid.git';
const entry = 'com.google.samples.apps.nowinandroid.core.designsystem.component.TagPreview';
const categories = ['language_semantics', 'standard_library', 'neutral_compose_widget', 'modifier', 'resources',
  'project_dependencies'];
const expectedCoverage = {
  language_semantics: { total: 112, recognized: 112, unsupported: 0, percentage: 100 },
  standard_library: { total: 16, recognized: 16, unsupported: 0, percentage: 100 },
  neutral_compose_widget: { total: 191, recognized: 178, unsupported: 13, percentage: 93.19 },
  modifier: { total: 0, recognized: 0, unsupported: 0, percentage: null },
  resources: { total: 0, recognized: 0, unsupported: 0, percentage: null },
  project_dependencies: { total: 0, recognized: 0, unsupported: 0, percentage: null },
};

mkdirSync(join(here, '.work'), { recursive: true });
const evidence = mkdtempSync(join(here, '.work/now-in-android-'));
const project = mkdtempSync('/tmp/kotlin-ets-now-in-android-');
spawnSync('rmdir', [project]);
console.log(`Evidence: ${evidence}`);

function run(label, command, args, options = {}, expected = 0) {
  const result = spawnSync(command, args, { encoding: 'utf8', timeout: 600000, maxBuffer: 32 * 1024 * 1024,
    ...options, env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC', ...options.env } });
  writeFileSync(join(evidence, `${label}.json`), JSON.stringify({ command, args, cwd: options.cwd,
    status: result.status, stdout: result.stdout, stderr: result.stderr }, null, 2));
  if (result.error) throw result.error;
  assert.equal(result.status, expected, result.stdout + result.stderr);
  return result;
}

function assertSource(source) {
  assert.ok(source.file);
  assert.ok(source.start >= 0);
  assert.ok(source.end >= source.start);
  assert.ok(source.line > 0 && source.column > 0);
  assert.ok(source.endLine > 0 && source.endColumn > 0);
}

assert.match(run('origin', 'git', ['-C', seed, 'remote', 'get-url', 'origin']).stdout.trim(),
  /github\.com[:/]android\/nowinandroid(?:\.git)?$/);
assert.equal(run('revision', 'git', ['-C', seed, 'rev-parse', revision]).stdout.trim(), revision);
run('detached-worktree', 'git', ['-C', seed, 'worktree', 'add', '--detach', project, revision]);

try {
  const androidHome = process.env.ANDROID_HOME ?? join(process.env.HOME, 'Library/Android/sdk');
  assert.ok(existsSync(join(androidHome, 'platforms/android-35/android.jar')), `Android 35 SDK missing: ${androidHome}`);
  // This project pins G1GC in gradle.properties; do not add the compiler
  // harness's SerialGC option to its Gradle daemon.
  const projectEnv = { ANDROID_HOME: androidHome, JAVA_TOOL_OPTIONS: '' };
  const projectRun = join(evidence, 'project-run');
  const output = join(evidence, 'TagPreview.ets');
  const reportPath = join(evidence, 'core-profile.json');
  const compilation = run('project-preflight', 'node', [join(root, 'project.mjs'), '--project', project,
    '--module', ':core:designsystem', '--variant', 'demoDebug', '--mode', 'page',
    '--unsupported-policy', 'error', '--entry', entry, '--out', output, '--preflight-out', reportPath,
    '--work-dir', projectRun, '--offline'], { env: projectEnv }, 2);
  const backendBlocker = JSON.parse(compilation.stdout);
  assert.equal(backendBlocker.code, 'UNSUPPORTED');
  assert.equal(backendBlocker.message,
    'Color.Unspecified requires inherited/default color selection; it is not an ARGB value');
  assert.equal(backendBlocker.source.line, 29);
  assert.equal(backendBlocker.source.column, 30);
  assert.equal(existsSync(output), false);

  const inputs = JSON.parse(readFileSync(join(projectRun, 'inputs.json'), 'utf8'));
  assert.equal(inputs.compilerVersion, '2.1.10');
  assert.equal(inputs.task, ':core:designsystem:compileDemoDebugKotlin');
  assert.equal(inputs.sources.length, 23);
  assert.equal(inputs.classpath.length, 54);
  const environment = JSON.parse(readFileSync(join(projectRun, 'compiler-environment.json'), 'utf8'));
  assert.equal(environment.projectCompilerVersion, '2.1.10');
  assert.equal(environment.frontendCompilerVersion, '2.1.20');
  assert.equal(environment.compatibilityDecision, 'same_language_line_older_patch');

  const report = JSON.parse(readFileSync(reportPath, 'utf8'));
  assert.equal(report.schemaVersion, 2);
  assert.equal(report.projectCompilerVersion, '2.1.10');
  assert.equal(report.frontendCompilerVersion, '2.1.20');
  assert.equal(report.compatibilityDecision, 'same_language_line_older_patch');
  assert.deepEqual(Object.keys(report.coverage), categories);
  assert.deepEqual(report.counts, Object.fromEntries(categories.map(category =>
    [category, expectedCoverage[category].total])));
  assert.deepEqual(report.coverage, expectedCoverage);
  assert.equal(report.calls.length, 319);
  const themeMode = report.calls.find(call =>
    call.finalRecognizedNode.symbol === 'androidx.compose.foundation.isSystemInDarkTheme');
  assert.equal(themeMode?.expectedTargetType, 'boolean');
  assert.equal(themeMode?.finalRecognizedNode.kind, 'typed_call');
  assert.equal(themeMode?.firstUnsupportedNode, null);
  const colorCopies = report.calls.filter(call =>
    call.finalRecognizedNode.symbol === 'androidx.compose.ui.graphics.Color.copy');
  assert.equal(colorCopies.length, 2);
  assert.ok(colorCopies.every(call => call.expectedTargetType === 'number' &&
    call.finalRecognizedNode.kind === 'typed_call' && call.firstUnsupportedNode === null));
  assert.ok(colorCopies.every(call => JSON.stringify(call.argumentResolutions) === JSON.stringify([
    { parameter: 'red', resolution: 'source_default' },
    { parameter: 'green', resolution: 'source_default' },
    { parameter: 'blue', resolution: 'source_default' },
  ])));
  const textStyleProvider = report.calls.find(call =>
    call.finalRecognizedNode.symbol === 'androidx.compose.material3.ProvideTextStyle');
  assert.equal(textStyleProvider?.expectedTargetType, 'void');
  assert.equal(textStyleProvider?.finalRecognizedNode.kind, 'typed_call');
  assert.equal(textStyleProvider?.firstUnsupportedNode, null);
  assert.equal(textStyleProvider?.source.line, 57);
  assert.equal(textStyleProvider?.source.column, 13);
  const surfaceColor = report.calls.find(call =>
    call.finalRecognizedNode.symbol === 'androidx.compose.material3.surfaceColorAtElevation');
  assert.equal(surfaceColor?.expectedTargetType, 'number');
  assert.equal(surfaceColor?.finalRecognizedNode.kind, 'typed_call');
  assert.equal(surfaceColor?.firstUnsupportedNode, null);
  assert.equal(surfaceColor?.source.line, 210);
  assert.equal(surfaceColor?.source.column, 70);
  const compositionLocalProvider = report.calls.find(call =>
    call.finalRecognizedNode.symbol === 'androidx.compose.runtime.CompositionLocalProvider');
  assert.equal(compositionLocalProvider?.expectedTargetType, 'void');
  assert.equal(compositionLocalProvider?.finalRecognizedNode.kind, 'typed_call');
  assert.equal(compositionLocalProvider?.firstUnsupportedNode, null);
  assert.equal(compositionLocalProvider?.source.line, 236);
  assert.equal(compositionLocalProvider?.source.column, 5);
  const providedValues = report.calls.filter(call =>
    call.finalRecognizedNode.symbol === 'androidx.compose.runtime.ProvidableCompositionLocal.provides');
  assert.deepEqual(providedValues.map(call => call.expectedTargetType), [
    'EtsProvidedValue<GradientColors>',
    'EtsProvidedValue<BackgroundTheme>',
    'EtsProvidedValue<TintTheme>',
  ]);
  assert.ok(providedValues.every(call => call.finalRecognizedNode.kind === 'typed_call' &&
    call.firstUnsupportedNode === null));
  assert.equal(report.firstUnsupportedNode.kind, 'target_type');
  assert.equal(report.firstUnsupportedNode.symbol,
    'androidx.compose.ui.text.style.LineHeightStyle.Alignment.Companion.<get-Bottom>');
  assert.match(report.firstUnsupportedNode.message, /Unsupported language type:.*LineHeightStyle\.Alignment/);
  assert.equal(report.firstUnsupportedNode.source.line, 67);
  assert.equal(report.firstUnsupportedNode.source.column, 35);
  assertSource(report.firstUnsupportedNode.source);

  for (const call of report.calls) {
    assertSource(call.source);
    assert.ok(call.finalRecognizedNode?.symbol);
    assertSource(call.finalRecognizedNode.source);
    assert.equal(call.finalRecognizedNode.source.start, call.source.start);
    assert.equal(call.finalRecognizedNode.source.end, call.source.end);
    assert.ok(Object.hasOwn(call, 'firstUnsupportedNode'));
    assert.ok(call.responsibleModule.startsWith('tools/kotlin-ets/src/'));
    if (call.firstUnsupportedNode) {
      assertSource(call.firstUnsupportedNode.source);
      assert.ok(call.firstUnsupportedNode.responsibleModule.startsWith('tools/kotlin-ets/src/'));
    }
  }

  const unsupportedCalls = report.calls.filter(call => call.firstUnsupportedNode !== null);
  assert.equal(unsupportedCalls.length, 13);
  assert.equal(unsupportedCalls.filter(call => call.firstUnsupportedNode.kind === 'target_type').length, 12);
  assert.equal(unsupportedCalls.filter(call => call.firstUnsupportedNode.kind === 'unsupported_call').length, 1);
  assert.ok(unsupportedCalls.every(call => call.category === 'neutral_compose_widget'));

  const baseline = {
    schemaVersion: 1,
    project: { repository, revision, entry, module: ':core:designsystem', variant: 'demoDebug', task: inputs.task },
    compiler: { project: report.projectCompilerVersion, frontend: report.frontendCompilerVersion,
      compatibilityDecision: report.compatibilityDecision },
    inputs: { sources: inputs.sources.length, classpathEntries: inputs.classpath.length },
    counts: report.counts,
    coverage: report.coverage,
    firstUnsupportedNode: report.firstUnsupportedNode,
    backendBlocker,
    unsupportedCalls,
    p0Gaps: [
      { category: 'neutral_compose_widget', node: 'androidx.compose.ui.graphics.Color.Unspecified',
        responsibleModule: 'tools/kotlin-ets/src/ui/ColorValueRule.kt', source: backendBlocker.source,
        detail: backendBlocker.message },
      { category: 'neutral_compose_widget', node: 'unsupported_call_inventory',
        responsibleModule: 'tools/kotlin-ets/src/ui/compose/ComposeWidgetAdapter.kt',
        counts: { target_type: 12, unsupported_call: 1 },
        detail: 'Thirteen source-linked Compose calls remain unsupported; all records are preserved in unsupportedCalls.' },
    ],
  };
  writeFileSync(join(evidence, 'public-project-baseline.json'), JSON.stringify(baseline, null, 2) + '\n');
  console.log('PASS Now in Android 5e34fb49: Kotlin 2.1.10 project enters the formal 2.1.20 frontend');
  console.log('PASS typed CompositionLocalProvider and provides calls advance the backend to Color.Unspecified; all 13 unsupported Compose calls remain explicit');
} finally {
  run('remove-worktree', 'git', ['-C', seed, 'worktree', 'remove', '--force', project]);
}
