import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import test from 'node:test';
import { parseOptions, readInputs, gradleArguments } from '../../project.mjs';

const launcher = fileURLToPath(new URL('../../kotlin-ets', import.meta.url));

test('page policy defaults to report, language stays strict and explicit strict is retained', () => {
  const base = ['--project', '/tmp/p', '--module', ':app', '--variant', 'debug',
    '--entry', 'sample.Page', '--out', '/tmp/Page.ets'];
  assert.equal(parseOptions(base).unsupportedPolicy, 'report');
  assert.equal(parseOptions([...base, '--unsupported-policy', 'error']).unsupportedPolicy, 'error');
  assert.equal(parseOptions([...base, '--mode', 'language']).unsupportedPolicy, 'error');
  assert.throws(() => parseOptions([...base, '--unsupported-policy', 'ignore']));
  assert.throws(() => parseOptions([...base, '--mode', 'language', '--unsupported-policy', 'report']));
});

test('project entry selects one module/variant and keeps paths with spaces intact', () => {
  const options = parseOptions(['--project', '/tmp/Android project', '--module', ':feature:onboarding',
    '--variant', 'demoDebug', '--entry', 'sample.OnBoardingScreen', '--out', '/tmp/ETS output/Page.ets', '--offline']);
  assert.equal(options.compileTask, 'compileDemoDebugKotlin');
  assert.equal(options.mode, 'page');
  const args = gradleArguments(options, '/tmp/working dir/inputs.json');
  assert.ok(args.includes('-PkotlinEtsModule=:feature:onboarding'));
  assert.ok(args.includes('-PkotlinEtsCompileTask=compileDemoDebugKotlin'));
  assert.ok(args.includes('-PkotlinEtsInputsOutput=/tmp/working dir/inputs.json'));
  assert.ok(args.includes('--offline'));
  assert.equal(args.at(-1), 'kotlinEtsCollectInputs');
});

test('explicit compile task supports non-Android modules, without variant guessing', () => {
  const options = parseOptions(['--project', '/tmp/p', '--module', ':', '--compile-task', 'compileKotlin', '--collect-only']);
  assert.equal(options.compileTask, 'compileKotlin');
  assert.equal(options.collectOnly, true);
  assert.ok(!gradleArguments(options, '/tmp/inputs.json').includes('--offline'));
});

test('project entry retains the materialized image registry path', () => {
  const options = parseOptions(['--project', '/tmp/p', '--module', ':app', '--variant', 'debug',
    '--entry', 'sample.Page', '--out', '/tmp/Page.ets', '--image-resources', '/tmp/image assets/image-resources.properties']);
  assert.equal(options.imageResources, '/tmp/image assets/image-resources.properties');
});

test('project entry retains the separate string resource input directory', () => {
  const options = parseOptions(['--project', '/tmp/p', '--module', ':app', '--variant', 'debug',
    '--entry', 'sample.Page', '--out', '/tmp/Page.ets', '--string-resources', '/tmp/string inputs']);
  assert.equal(options.stringResources, '/tmp/string inputs');
});

test('project entry retains the separate font registry path', () => {
  const options = parseOptions(['--project', '/tmp/p', '--module', ':app', '--variant', 'debug',
    '--entry', 'sample.Page', '--out', '/tmp/Page.ets', '--font-resources', '/tmp/font inputs/fonts.properties']);
  assert.equal(options.fontResources, '/tmp/font inputs/fonts.properties');
});

test('invalid or ambiguous project input is rejected before invoking Gradle', () => {
  const base = ['--project', '/tmp/p', '--module', ':app', '--variant', 'debug', '--entry', 'sample.Page', '--out', '/tmp/Page.ets'];
  for (const extra of [['--variant', 'release'], ['--classpath', 'other.jar'], ['--compile-task', 'compileKotlin'], ['--out-dir', '/tmp/modules']]) {
    assert.throws(() => parseOptions([...base, ...extra]));
  }
  assert.throws(() => parseOptions(['--project', '/tmp/p', '--module', ':app', '--collect-only']));
  assert.throws(() => parseOptions(['--project', '/tmp/p', '--module', ':app', '--variant', '../debug', '--collect-only']));
  assert.throws(() => parseOptions(['--project', '/tmp/p', '--module', ':app', '--variant', 'debug', '--out', '/tmp/P.ets']));
});

test('resolved manifest retains ordered transitive classpath and validates physical inputs', () => {
  const root = mkdtempSync(join(tmpdir(), 'kotlin-ets-project-contract-'));
  const source = join(root, 'Screen.kt');
  const java = join(root, 'Model.java');
  const jar = join(root, 'direct.jar');
  const transitive = join(root, 'transitive.jar');
  const classes = join(root, 'project classes');
  for (const file of [source, java, jar, transitive]) writeFileSync(file, 'fixture');
  mkdirSync(classes);
  const manifest = join(root, 'inputs.json');
  const value = { schemaVersion: 1, sources: [source, java], classpath: [transitive, jar, classes] };
  writeFileSync(manifest, JSON.stringify(value));
  assert.deepEqual(readInputs(manifest), value);
  writeFileSync(manifest, JSON.stringify({ ...value, classpath: [join(root, 'missing.jar')] }));
  assert.throws(() => readInputs(manifest), /missing|exist/i);
  writeFileSync(manifest, JSON.stringify({ ...value, sources: [java] }));
  assert.throws(() => readInputs(manifest), /Kotlin/);
  writeFileSync(manifest, JSON.stringify({ ...value, sources: ['relative.kt'] }));
  assert.throws(() => readInputs(manifest), /absolute/);
  assert.equal(readFileSync(source, 'utf8'), 'fixture');
});

test('public launcher rejects missing wrapper without invoking the compiler', () => {
  const result = spawnSync('bash', [launcher, '--project', '/does-not-exist/kotlin-ets', '--module', ':app', '--variant', 'debug', '--collect-only'], { encoding: 'utf8' });
  assert.equal(result.status, 1);
  const diagnostic = JSON.parse(result.stdout);
  assert.equal(diagnostic.code, 'PROJECT_INPUTS_FAILED');
  assert.equal(diagnostic.stage, 'configuration');
  assert.match(diagnostic.message, /wrapper missing/);
});

test('public launcher preserves Gradle failure logs, never emits a target', () => {
  const project = mkdtempSync(join(tmpdir(), 'kotlin-ets-gradle-failure-'));
  writeFileSync(join(project, 'gradlew'), '#!/usr/bin/env bash\nprintf "missing transitive artifact\\n" >&2\nexit 7\n');
  const result = spawnSync('bash', [launcher, '--project', project, '--module', ':app', '--variant', 'debug', '--collect-only'], { encoding: 'utf8' });
  assert.equal(result.status, 1);
  const diagnostic = JSON.parse(result.stdout);
  assert.equal(diagnostic.stage, 'gradle');
  assert.match(diagnostic.message, /exit 7/);
  assert.match(readFileSync(join(diagnostic.workDir, 'gradle.stderr.log'), 'utf8'), /missing transitive artifact/);
});

test('public launcher refuses existing targets before Gradle executes', () => {
  const project = mkdtempSync(join(tmpdir(), 'kotlin-ets-gradle-no-overwrite-'));
  writeFileSync(join(project, 'gradlew'), '#!/usr/bin/env bash\nexit 99\n');
  const output = join(project, 'Page.ets');
  writeFileSync(output, 'user code');
  const result = spawnSync('bash', [launcher, '--project', project, '--module', ':app', '--variant', 'debug', '--entry', 'sample.Page', '--out', output], { encoding: 'utf8' });
  assert.equal(result.status, 1);
  assert.match(JSON.parse(result.stdout).message, /Refusing to overwrite/);
  assert.equal(readFileSync(output, 'utf8'), 'user code');
});
