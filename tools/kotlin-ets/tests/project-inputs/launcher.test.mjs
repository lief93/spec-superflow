import assert from 'node:assert/strict';
import { existsSync, mkdtempSync, mkdirSync, writeFileSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import test from 'node:test';
import { parseOptions, readInputs, gradleArguments } from '../../project.mjs';

const launcher = fileURLToPath(new URL('../../kotlin-ets', import.meta.url));

test('project collection merges explicitly supplied dependency sources without changing Gradle inputs', () => {
  const project = mkdtempSync(join(tmpdir(), 'kotlin-ets-dependency-sources-'));
  const source = join(project, 'App.kt');
  const library = join(project, 'Library.kt');
  const jar = join(project, 'library.jar');
  for (const path of [source, library, jar]) writeFileSync(path, 'fixture');
  const manifest = { schemaVersion: 1, sources: [source], classpath: [jar] };
  writeFileSync(join(project, 'gradlew'), `#!/usr/bin/env bash\nfor arg in "$@"; do\n  case "$arg" in\n    -PkotlinEtsInputsOutput=*) printf '%s' '${JSON.stringify(manifest)}' > "\${arg#*=}" ;;\n  esac\ndone\n`);
  const list = join(project, 'dependency sources.txt');
  writeFileSync(list, `${library}\n${source}\n${library}\n`);
  const result = spawnSync('bash', [launcher, '--project', project, '--module', ':', '--compile-task', 'compileKotlin',
    '--collect-only', '--dependency-sources-file', list], { encoding: 'utf8' });
  assert.equal(result.status, 0, result.stdout + result.stderr);
  const output = JSON.parse(result.stdout);
  assert.equal(output.sourceCount, 2);
  assert.deepEqual(JSON.parse(readFileSync(output.inputs)), manifest);
  assert.equal(readFileSync(join(output.inputs, '..', 'sources.txt'), 'utf8'), `${source}\n${library}\n`);
});

test('dependency sources reject missing or non-source entries before Gradle executes', () => {
  const project = mkdtempSync(join(tmpdir(), 'kotlin-ets-invalid-dependency-'));
  writeFileSync(join(project, 'gradlew'), '#!/usr/bin/env bash\nexit 99\n');
  const list = join(project, 'sources.txt');
  writeFileSync(list, `${join(project, 'missing.kt')}\n`);
  const result = spawnSync('bash', [launcher, '--project', project, '--module', ':', '--compile-task', 'compileKotlin',
    '--collect-only', '--dependency-sources-file', list], { encoding: 'utf8' });
  assert.equal(result.status, 1);
  const diagnostic = JSON.parse(result.stdout);
  assert.equal(diagnostic.stage, 'configuration');
  assert.match(diagnostic.message, /missing\.kt/);
});

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
  assert.ok(args.includes('-PkotlinEtsVariant=demoDebug'));
  assert.ok(args.includes('-PkotlinEtsInputsOutput=/tmp/working dir/inputs.json'));
  assert.ok(args.includes('--offline'));
  assert.equal(args.at(-1), ':feature:onboarding:kotlinEtsCollectInputs');
});

test('explicit compile task supports non-Android modules, without variant guessing', () => {
  const options = parseOptions(['--project', '/tmp/p', '--module', ':', '--compile-task', 'compileKotlin', '--collect-only']);
  assert.equal(options.compileTask, 'compileKotlin');
  assert.equal(options.collectOnly, true);
  assert.equal(gradleArguments(options, '/tmp/inputs.json').at(-1), ':kotlinEtsCollectInputs');
  assert.ok(!gradleArguments(options, '/tmp/inputs.json').includes('--offline'));
  assert.ok(!gradleArguments(options, '/tmp/inputs.json').some(argument => argument.startsWith('-PkotlinEtsVariant=')));
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

test('project entry retains the Core Profile preflight report path', () => {
  const options = parseOptions(['--project', '/tmp/p', '--module', ':app', '--variant', 'debug',
    '--entry', 'sample.Page', '--out', '/tmp/Page.ets', '--preflight-out', '/tmp/reports/core profile.json']);
  assert.equal(options.preflightOutput, '/tmp/reports/core profile.json');
});

test('project entry rejects a Core Profile report inside the target path', () => {
  const base = ['--project', '/tmp/p', '--module', ':app', '--variant', 'debug', '--entry', 'sample.Page'];
  assert.throws(() => parseOptions([...base, '--out', '/tmp/Page.ets', '--preflight-out', '/tmp/Page.ets']),
    /Preflight report must be outside the target path/);
  assert.throws(() => parseOptions([...base, '--out-dir', '/tmp/generated', '--preflight-out', '/tmp/generated/profile.json']),
    /Preflight report must be outside the target path/);
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
  const resources = join(root, 'src/main/res');
  const symbols = join(root, 'R.txt');
  for (const file of [source, java, jar, transitive]) writeFileSync(file, 'fixture');
  mkdirSync(classes); mkdirSync(resources, { recursive: true }); writeFileSync(symbols, 'int drawable image 0x7f040001\n');
  const manifest = join(root, 'inputs.json');
  const value = { schemaVersion: 2, sources: [source, java], classpath: [transitive, jar, classes],
    resourceInputs: { namespace: 'sample.app', variant: 'debug', symbols,
      roots: [{ sourceSet: 'main', overlayPriority: 0, path: resources }] } };
  writeFileSync(manifest, JSON.stringify(value));
  assert.deepEqual(readInputs(manifest), value);
  writeFileSync(manifest, JSON.stringify({ ...value, classpath: [join(root, 'missing.jar')] }));
  assert.throws(() => readInputs(manifest), /missing|exist/i);
  writeFileSync(manifest, JSON.stringify({ ...value, sources: [java] }));
  assert.throws(() => readInputs(manifest), /Kotlin/);
  writeFileSync(manifest, JSON.stringify({ ...value, sources: ['relative.kt'] }));
  assert.throws(() => readInputs(manifest), /absolute/);
  writeFileSync(manifest, JSON.stringify({ ...value, resourceInputs: { ...value.resourceInputs,
    roots: [{ sourceSet: 'debug', overlayPriority: -1, path: resources }] } }));
  assert.throws(() => readInputs(manifest), /resource/);
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

test('incompatible project compiler version fails at the project boundary without report or ETS', () => {
  const project = mkdtempSync(join(tmpdir(), 'kotlin-ets-incompatible-version-'));
  const source = join(project, 'App.kt');
  const jar = join(project, 'dependency.jar');
  writeFileSync(source, 'fun value() = 1\n');
  writeFileSync(jar, 'fixture');
  const manifest = { schemaVersion: 1, sources: [source], classpath: [jar], compilerVersion: '2.2.0',
    compilerArguments: [] };
  writeFileSync(join(project, 'gradlew'), `#!/usr/bin/env bash\nfor arg in "$@"; do\n  case "$arg" in\n    -PkotlinEtsInputsOutput=*) printf '%s' '${JSON.stringify(manifest)}' > "\${arg#*=}" ;;\n  esac\ndone\n`);
  const output = join(project, 'out.ets');
  const preflight = join(project, 'preflight.json');
  const result = spawnSync('bash', [launcher, '--project', project, '--module', ':', '--compile-task', 'compileKotlin',
    '--mode', 'language', '--out', output, '--preflight-out', preflight], { encoding: 'utf8' });
  assert.equal(result.status, 1);
  const diagnostic = JSON.parse(result.stdout);
  assert.equal(diagnostic.stage, 'compiler-environment');
  assert.match(diagnostic.message, /project 2\.2\.0, ETS frontend 2\.1\.20/);
  assert.equal(existsSync(output), false);
  assert.equal(existsSync(preflight), false);
});

test('same-priority project image definitions fail before compiler execution without ETS', () => {
  const project = mkdtempSync(join(tmpdir(), 'kotlin-ets-duplicate-images-'));
  const source = join(project, 'App.kt');
  const jar = join(project, 'dependency.jar');
  const first = join(project, 'first-res');
  const second = join(project, 'second-res');
  const symbols = join(project, 'R.txt');
  writeFileSync(source, 'fun value() = 1\n'); writeFileSync(jar, 'fixture');
  for (const root of [first, second]) {
    mkdirSync(join(root, 'drawable'), { recursive: true });
    writeFileSync(join(root, 'drawable/repeated.png'), 'fixture');
  }
  writeFileSync(symbols, 'int drawable repeated 0x7f040001\n');
  const manifest = { schemaVersion: 2, sources: [source], classpath: [jar], compilerVersion: '2.1.20',
    compilerArguments: [], resourceInputs: { namespace: 'sample', variant: 'debug', symbols, roots: [
      { sourceSet: 'main', overlayPriority: 0, path: first },
      { sourceSet: 'main', overlayPriority: 0, path: second },
    ] } };
  writeFileSync(join(project, 'gradlew'), `#!/usr/bin/env bash\nfor arg in "$@"; do\n  case "$arg" in\n    -PkotlinEtsInputsOutput=*) printf '%s' '${JSON.stringify(manifest)}' > "\${arg#*=}" ;;\n  esac\ndone\n`);
  const output = join(project, 'out.ets');
  const preflight = join(project, 'preflight.json');
  const result = spawnSync('bash', [launcher, '--project', project, '--module', ':app', '--variant', 'debug',
    '--entry', 'sample.Page', '--out', output, '--preflight-out', preflight], { encoding: 'utf8' });
  assert.equal(result.status, 1);
  const diagnostic = JSON.parse(result.stdout);
  assert.equal(diagnostic.stage, 'image-resources');
  assert.match(diagnostic.message, /Ambiguous project image resource sample\.R\.drawable\.repeated/);
  assert.equal(existsSync(output), false);
  assert.equal(existsSync(preflight), false);
});

test('same-priority project string definitions fail before compiler execution without ETS', () => {
  const project = mkdtempSync(join(tmpdir(), 'kotlin-ets-duplicate-strings-'));
  const source = join(project, 'App.kt');
  const jar = join(project, 'dependency.jar');
  const first = join(project, 'first-res');
  const second = join(project, 'second-res');
  const symbols = join(project, 'R.txt');
  writeFileSync(source, 'fun value() = 1\n'); writeFileSync(jar, 'fixture');
  for (const [root, value] of [[first, 'First'], [second, 'Second']]) {
    mkdirSync(join(root, 'values'), { recursive: true });
    writeFileSync(join(root, 'values/strings.xml'), `<resources><string name="repeated">${value}</string></resources>`);
  }
  writeFileSync(symbols, 'int string repeated 0x7f010001\n');
  const manifest = { schemaVersion: 2, sources: [source], classpath: [jar], compilerVersion: '2.1.20',
    compilerArguments: [], resourceInputs: { namespace: 'sample', variant: 'debug', symbols, roots: [
      { sourceSet: 'main', overlayPriority: 0, path: first },
      { sourceSet: 'main', overlayPriority: 0, path: second },
    ] } };
  writeFileSync(join(project, 'gradlew'), `#!/usr/bin/env bash\nfor arg in "$@"; do\n  case "$arg" in\n    -PkotlinEtsInputsOutput=*) printf '%s' '${JSON.stringify(manifest)}' > "\${arg#*=}" ;;\n  esac\ndone\n`);
  const output = join(project, 'out.ets');
  const preflight = join(project, 'preflight.json');
  const result = spawnSync('bash', [launcher, '--project', project, '--module', ':app', '--variant', 'debug',
    '--entry', 'sample.Page', '--out', output, '--preflight-out', preflight], { encoding: 'utf8' });
  assert.equal(result.status, 1);
  const diagnostic = JSON.parse(result.stdout);
  assert.equal(diagnostic.stage, 'string-resources');
  assert.match(diagnostic.message, /Ambiguous project string resource sample\.R\.string\.repeated/);
  assert.equal(existsSync(output), false);
  assert.equal(existsSync(preflight), false);
});
