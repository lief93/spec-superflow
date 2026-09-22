import assert from 'node:assert/strict';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../..');
const seed = process.argv[2] && resolve(process.argv[2]);
assert.ok(seed && existsSync(join(seed, '.git')),
  'Usage: node architecture-samples.mjs /absolute/path/to/architecture-samples-checkout');

const revision = 'ee66e1526b84c026615df032c705842b7d2a521f';
const repository = 'https://github.com/android/architecture-samples.git';
const entry = 'com.example.android.architecture.blueprints.todoapp.statistics.StatisticsScreen';
const categories = ['language_semantics', 'standard_library', 'neutral_compose_widget', 'modifier', 'resources',
  'project_dependencies'];
const expectedCoverage = {
  language_semantics: { total: 32, recognized: 31, unsupported: 1, percentage: 96.87 },
  standard_library: { total: 51, recognized: 51, unsupported: 0, percentage: 100 },
  neutral_compose_widget: { total: 15, recognized: 12, unsupported: 3, percentage: 80 },
  modifier: { total: 7, recognized: 7, unsupported: 0, percentage: 100 },
  resources: { total: 6, recognized: 6, unsupported: 0, percentage: 100 },
  project_dependencies: { total: 13, recognized: 6, unsupported: 7, percentage: 46.15 },
};

mkdirSync(join(here, '.work'), { recursive: true });
const evidence = mkdtempSync(join(here, '.work/architecture-samples-'));
const project = mkdtempSync('/tmp/kotlin-ets-architecture-samples-');
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
  /github\.com[:/]android\/architecture-samples(?:\.git)?$/);
assert.equal(run('revision', 'git', ['-C', seed, 'rev-parse', revision]).stdout.trim(), revision);
run('detached-worktree', 'git', ['-C', seed, 'worktree', 'add', '--detach', project, revision]);

try {
  const androidHome = process.env.ANDROID_HOME ?? join(process.env.HOME, 'Library/Android/sdk');
  assert.ok(existsSync(join(androidHome, 'platforms/android-35/android.jar')), `Android 35 SDK missing: ${androidHome}`);
  const projectRun = join(evidence, 'project-run');
  const output = join(evidence, 'StatisticsScreen.ets');
  const reportPath = join(evidence, 'core-profile.json');
  const compilation = run('project-preflight', 'node', [join(root, 'project.mjs'), '--project', project,
    '--module', ':app', '--variant', 'debug', '--mode', 'page', '--unsupported-policy', 'error', '--entry', entry,
    '--out', output, '--preflight-out', reportPath, '--work-dir', projectRun, '--offline'],
  { env: { ANDROID_HOME: androidHome } }, 2);
  const backendBlocker = JSON.parse(compilation.stdout);
  assert.equal(backendBlocker.code, 'UNSUPPORTED');
  assert.equal(backendBlocker.message, 'External inline call has no loaded IR body: ' +
    'androidx.hilt.navigation.compose.hiltViewModel. Provide explicit dependency source, a supported serialized ' +
    'dependency, or a declared typed adapter; this call has no usable binary IR body. ' +
    'JVM binary metadata contains no serialized IR. Unsupported external call: ' +
    'androidx.hilt.navigation.compose.hiltViewModel. Missing dependency body or declared typed adapter');
  assert.equal(backendBlocker.source.line, 47);
  assert.equal(backendBlocker.source.column, 38);
  assert.equal(existsSync(output), false);

  const inputs = JSON.parse(readFileSync(join(projectRun, 'inputs.json'), 'utf8'));
  assert.equal(inputs.compilerVersion, '2.1.10');
  assert.equal(inputs.task, ':app:compileDebugKotlin');
  assert.equal(inputs.sources.length, 85);
  assert.equal(inputs.classpath.length, 89);
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
  assert.equal(report.calls.length, 124);
  assert.equal(report.firstUnsupportedNode.kind, 'target_type');
  assert.equal(report.firstUnsupportedNode.symbol, 'androidx.compose.runtime.remember');
  assert.match(report.firstUnsupportedNode.message, /SnackbarHostState/);
  assert.equal(report.firstUnsupportedNode.source.line, 48);
  assert.equal(report.firstUnsupportedNode.source.column, 44);
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
  assert.equal(unsupportedCalls.length, 11);
  assert.deepEqual(Object.fromEntries(categories.map(category => [category,
    unsupportedCalls.filter(call => call.category === category).length])), {
    language_semantics: 1, standard_library: 0, neutral_compose_widget: 3,
    modifier: 0, resources: 0, project_dependencies: 7,
  });

  const baseline = {
    schemaVersion: 1,
    project: { repository, revision, entry, module: ':app', variant: 'debug', task: inputs.task },
    compiler: { project: report.projectCompilerVersion, frontend: report.frontendCompilerVersion,
      compatibilityDecision: report.compatibilityDecision },
    inputs: { sources: inputs.sources.length, classpathEntries: inputs.classpath.length },
    counts: report.counts,
    coverage: report.coverage,
    firstUnsupportedNode: report.firstUnsupportedNode,
    backendBlocker,
    unsupportedCalls,
    p0Gaps: [
      { category: 'project_dependencies', node: 'androidx.hilt.navigation.compose.hiltViewModel',
        responsibleModule: 'tools/kotlin-ets/src/adapters/AdapterModules.kt', source: backendBlocker.source,
        detail: backendBlocker.message },
      { category: 'six_category_coverage', node: 'unsupported_call_inventory',
        responsibleModules: [...new Set(unsupportedCalls.map(call => call.responsibleModule))].sort(),
        counts: { language_semantics: 1, neutral_compose_widget: 3, project_dependencies: 7 },
        detail: 'Eleven source-linked calls remain unsupported; the report\'s designated first type gap is remember returning SnackbarHostState.' },
    ],
  };
  writeFileSync(join(evidence, 'public-project-baseline.json'), JSON.stringify(baseline, null, 2) + '\n');
  console.log('PASS architecture-samples ee66e152: Kotlin 2.1.10 project enters the formal 2.1.20 frontend');
  console.log('PASS 124-call six-category baseline; dependency body and all 11 unsupported calls remain explicit');
} finally {
  run('remove-worktree', 'git', ['-C', seed, 'worktree', 'remove', '--force', project]);
}
