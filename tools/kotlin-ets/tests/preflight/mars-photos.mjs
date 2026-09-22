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
  const projectRun = join(evidence, 'project-run');
  const output = join(evidence, 'LoadingScreen.ets');
  const reportPath = join(evidence, 'core-profile.json');
  const compilation = run('project-preflight', 'node', [join(root, 'project.mjs'), '--project', project,
    '--module', ':app', '--variant', 'debug', '--mode', 'page', '--unsupported-policy', 'error', '--entry', entry,
    '--out', output, '--preflight-out', reportPath, '--work-dir', projectRun, '--offline'],
  { env: { ANDROID_HOME: androidHome } }, 2);
  assert.equal(JSON.parse(compilation.stdout).code, 'UNSUPPORTED');
  assert.equal(existsSync(output), false);

  const inputs = JSON.parse(readFileSync(join(projectRun, 'inputs.json'), 'utf8'));
  assert.equal(inputs.schemaVersion, 2);
  assert.equal(inputs.compilerVersion, '2.1.0');
  assert.equal(inputs.resourceInputs.namespace, 'com.example.marsphotos');
  assert.equal(inputs.resourceInputs.variant, 'debug');
  assert.ok(inputs.resourceInputs.roots.some(root => root.sourceSet === 'main' && root.path.endsWith('/app/src/main/res')));
  assert.ok(inputs.resourceInputs.symbols.endsWith('/runtime_symbol_list/debug/processDebugResources/R.txt'));
  const environment = JSON.parse(readFileSync(join(projectRun, 'compiler-environment.json'), 'utf8'));
  assert.equal(environment.projectCompilerVersion, '2.1.0');
  assert.equal(environment.frontendCompilerVersion, '2.1.20');
  assert.equal(environment.compatibilityDecision, 'same_language_line_older_patch');
  const imagePack = JSON.parse(readFileSync(join(projectRun, 'image-resources.json'), 'utf8'));
  const imageProperties = readFileSync(imagePack.properties, 'utf8');
  assert.match(imageProperties, /com\.example\.marsphotos\.R\.drawable\.loading_img = img_[0-9a-f]{64}/);
  const imageOrigins = JSON.parse(readFileSync(imagePack.provenance, 'utf8'));
  const loadingImage = imageOrigins.resources.find(resource =>
    resource.symbol === 'com.example.marsphotos.R.drawable.loading_img');
  assert.equal(loadingImage.status, 'materialized');
  assert.equal(loadingImage.source.sourceSet, 'main');
  assert.ok(existsSync(join(imagePack.output, loadingImage.output)));
  assert.match(readFileSync(join(imagePack.output, loadingImage.output), 'utf8'), /^<svg/);

  const report = JSON.parse(readFileSync(reportPath, 'utf8'));
  assert.equal(report.schemaVersion, 2);
  assert.equal(report.projectCompilerVersion, '2.1.0');
  assert.equal(report.frontendCompilerVersion, '2.1.20');
  assert.equal(report.compatibilityDecision, 'same_language_line_older_patch');
  assert.deepEqual(Object.keys(report.coverage), ['language_semantics', 'standard_library', 'neutral_compose_widget',
    'modifier', 'resources', 'project_dependencies']);
  assert.deepEqual(report.counts, { language_semantics: 0, standard_library: 0, neutral_compose_widget: 2,
    modifier: 1, resources: 2, project_dependencies: 0 });
  assert.equal(report.coverage.neutral_compose_widget.percentage, 100);
  assert.equal(report.coverage.modifier.percentage, 100);
  assert.equal(report.coverage.resources.percentage, 50);
  const painter = report.calls.find(call => call.resolvedSymbol.startsWith('androidx.compose.ui.res.painterResource('));
  assert.ok(painter);
  assert.equal(painter.firstUnsupportedNode, null);
  assert.equal(painter.expectedTargetType, 'Resource');
  assert.equal(report.firstUnsupportedNode.source.line, 74);
  assert.equal(report.firstUnsupportedNode.source.column, 54);
  assert.equal(report.firstUnsupportedNode.kind, 'unsupported_expression');
  assert.equal(report.firstUnsupportedNode.symbol, null);
  assert.match(report.firstUnsupportedNode.message, /Dynamic stringResource ID/);
  assert.match(report.firstUnsupportedNode.responsibleModule, /StringResources/);
  for (const call of report.calls) {
    assert.ok(call.source.line > 0 && call.source.column > 0);
    assert.ok(call.finalRecognizedNode?.symbol);
    assert.ok(Object.hasOwn(call, 'firstUnsupportedNode'));
    assert.ok(call.responsibleModule);
  }

  const baseline = {
    schemaVersion: 1,
    project: { repository, revision, entry },
    compiler: { project: report.projectCompilerVersion, frontend: report.frontendCompilerVersion,
      compatibilityDecision: report.compatibilityDecision },
    coverage: report.coverage,
    p0Gaps: [
      { category: 'resources', node: 'com.example.marsphotos.R.string.loading',
        responsibleModule: report.firstUnsupportedNode.responsibleModule, source: report.firstUnsupportedNode.source,
        detail: report.firstUnsupportedNode.message },
    ],
  };
  writeFileSync(join(evidence, 'public-project-baseline.json'), JSON.stringify(baseline, null, 2) + '\n');
  console.log('PASS Mars Photos 8399c839: variant-aware loading_img VectorDrawable materializes through the formal project path');
  console.log('PASS no target: next real stringResource gap remains explicit');
} finally {
  run('remove-worktree', 'git', ['-C', seed, 'worktree', 'remove', '--force', project]);
}
