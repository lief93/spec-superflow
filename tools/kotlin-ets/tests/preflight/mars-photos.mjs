import assert from 'node:assert/strict';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../..');
const seed = process.argv[2] && resolve(process.argv[2]);
assert.ok(seed && existsSync(join(seed, '.git')), 'Usage: node mars-photos.mjs /absolute/path/to/mars-photos-checkout');

const revision = '8399c839ce5f4be66e0ae1103ed0e04121c97fe4';
const repository = 'https://github.com/google-developer-training/basic-android-kotlin-compose-training-mars-photos.git';
const entry = 'com.example.marsphotos.ui.screens.LoadingScreen';
mkdirSync(join(here, '.work'), { recursive: true });
const evidence = mkdtempSync(join(here, '.work/mars-photos-'));
const project = mkdtempSync('/tmp/kotlin-ets-mars-photos-');
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

assert.match(run('origin', 'git', ['-C', seed, 'remote', 'get-url', 'origin']).stdout.trim(),
  /github\.com[:/]google-developer-training\/basic-android-kotlin-compose-training-mars-photos(?:\.git)?$/);
assert.equal(run('revision', 'git', ['-C', seed, 'rev-parse', revision]).stdout.trim(), revision);
run('detached-worktree', 'git', ['-C', seed, 'worktree', 'add', '--detach', project, revision]);

try {
  const androidHome = process.env.ANDROID_HOME ?? join(process.env.HOME, 'Library/Android/sdk');
  assert.ok(existsSync(join(androidHome, 'platforms/android-35/android.jar')), `Android 35 SDK missing: ${androidHome}`);
  const collected = join(evidence, 'project-inputs');
  const collection = run('collect', 'node', [join(root, 'project.mjs'), '--project', project, '--module', ':app',
    '--variant', 'debug', '--collect-only', '--work-dir', collected, '--offline'], { env: { ANDROID_HOME: androidHome } });
  const collectionResult = JSON.parse(collection.stdout);
  assert.equal(collectionResult.ok, true);
  const inputs = JSON.parse(readFileSync(collectionResult.inputs, 'utf8'));
  assert.equal(inputs.compilerVersion, '2.1.0');

  const output = join(evidence, 'LoadingScreen.ets');
  const reportPath = join(evidence, 'core-profile.json');
  const compilation = run('preflight', 'bash', [join(root, 'kotlin-ets'), '--mode', 'page',
    '--unsupported-policy', 'error', '--entry', entry, '--classpath-file', join(collected, 'classpath.txt'),
    '--sources-file', join(collected, 'sources.txt'), '--out', output, '--preflight-out', reportPath], {}, 2);
  assert.equal(JSON.parse(compilation.stdout).code, 'UNSUPPORTED');
  assert.equal(existsSync(output), false);

  const report = JSON.parse(readFileSync(reportPath, 'utf8'));
  assert.equal(report.schemaVersion, 2);
  assert.deepEqual(Object.keys(report.coverage), ['language_semantics', 'standard_library', 'neutral_compose_widget',
    'modifier', 'resources', 'project_dependencies']);
  assert.deepEqual(report.counts, { language_semantics: 0, standard_library: 0, neutral_compose_widget: 2,
    modifier: 1, resources: 2, project_dependencies: 0 });
  assert.equal(report.coverage.neutral_compose_widget.percentage, 100);
  assert.equal(report.coverage.modifier.percentage, 100);
  assert.equal(report.coverage.resources.percentage, 50);
  assert.equal(report.firstUnsupportedNode.source.line, 73);
  assert.equal(report.firstUnsupportedNode.source.column, 46);
  assert.equal(report.firstUnsupportedNode.kind, 'unsupported_expression');
  assert.equal(report.firstUnsupportedNode.symbol, null);
  assert.match(report.firstUnsupportedNode.message, /Dynamic painterResource ID/);
  assert.match(report.firstUnsupportedNode.responsibleModule, /ImageResources/);
  for (const call of report.calls) {
    assert.ok(call.source.line > 0 && call.source.column > 0);
    assert.ok(call.finalRecognizedNode?.symbol);
    assert.ok(Object.hasOwn(call, 'firstUnsupportedNode'));
    assert.ok(call.responsibleModule);
  }

  const baseline = {
    schemaVersion: 1,
    project: { repository, revision, entry },
    compiler: { project: inputs.compilerVersion, coverageFrontend: '2.1.20' },
    coverage: report.coverage,
    p0Gaps: [
      { category: 'project_dependencies', node: 'compiler_environment', responsibleModule: 'tools/kotlin-ets/compiler-environment.mjs',
        detail: 'The public project pins Kotlin 2.1.0; production project generation requires 2.1.20.' },
      { category: 'resources', node: 'com.example.marsphotos.R.drawable.loading_img',
        responsibleModule: report.firstUnsupportedNode.responsibleModule, source: report.firstUnsupportedNode.source,
        detail: report.firstUnsupportedNode.message },
    ],
  };
  writeFileSync(join(evidence, 'public-project-baseline.json'), JSON.stringify(baseline, null, 2) + '\n');
  console.log('PASS Mars Photos 8399c839: production input collection and Core Profile coverage baseline');
  console.log('PASS no target: compiler-version mismatch and first resource gap remain explicit P0 records');
} finally {
  run('remove-worktree', 'git', ['-C', seed, 'worktree', 'remove', '--force', project]);
}
