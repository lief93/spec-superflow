import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, statSync, writeFileSync } from 'node:fs';
import { dirname, isAbsolute, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { compilerEnvironment } from '../../../compiler-environment.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../../..');
const script = join(root, 'project-inputs.gradle');
const host = resolve(process.env.COLLECTOR_ANDROID_HOST ?? '/private/tmp/kotlin-ets-native-20260914-06/android');
const java = '/Applications/Android Studio.app/Contents/jbr/Contents/Home';
const env = { ...process.env, JAVA_HOME: java, PATH: `${java}/bin:${process.env.PATH}`,
  JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC',
  ANDROID_HOME: process.env.ANDROID_HOME ?? '/Users/lief123/Library/Android/sdk' };
mkdirSync(join(here, '.work'), { recursive: true });
const work = mkdtempSync(join(here, '.work/run-'));
console.log(`Evidence: ${work}`);
const project = join(work, 'fixture');
cpSync(join(here, 'fixture'), project, { recursive: true });
function run(label, directory, module, task, extra = [], failure) {
  const output = join(work, `${label}-inputs.json`);
  const graph = join(work, `${label}-graph.json`);
  const args = [join(host, 'gradlew'), '-p', directory, '--no-daemon', '--no-configuration-cache', '--console=plain',
    '--offline', '--max-workers=2', '-Dorg.gradle.jvmargs=-Xmx1024m -XX:ActiveProcessorCount=2 -XX:+UseSerialGC',
    '-I', script, '-I', join(here, 'observe.gradle'), `-PkotlinEtsModule=${module}`, `-PkotlinEtsCompileTask=${task}`,
    `-PkotlinEtsInputsOutput=${output}`, `-PcollectorTestGraph=${graph}`, ...extra,
    module === ':' ? ':kotlinEtsCollectInputs' : `${module}:kotlinEtsCollectInputs`];
  const result = spawnSync('bash', args, { cwd: directory, env, encoding: 'utf8', timeout: 240000 });
  writeFileSync(join(work, `${label}-command.json`), JSON.stringify({ command: 'bash', args, status: result.status,
    stdout: result.stdout, stderr: result.stderr, error: result.error?.message }, null, 2));
  if (result.error) throw result.error;
  if (failure) {
    assert.notEqual(result.status, 0);
    assert.match(result.stdout + result.stderr, failure);
    assert.equal(existsSync(output), false);
    return;
  }
  assert.equal(result.status, 0, result.stdout + result.stderr);
  const data = JSON.parse(readFileSync(output));
  assert.equal(data.schemaVersion, 1);
  assert.equal(data.compilerVersion, '2.1.20');
  assert.ok(Array.isArray(data.compilerArguments));
  compilerEnvironment(data);
  assert.equal(data.project, directory);
  assert.equal(data.module, module);
  assert.equal(data.task, `${module === ':' ? '' : module}:${task}`);
  assert.ok(data.sources.length > 0);
  assert.ok(data.classpath.length > 0);
  for (const paths of [data.sources, data.classpath]) {
    assert.equal(new Set(paths).size, paths.length);
    for (const path of paths) { assert.ok(isAbsolute(path)); assert.ok(existsSync(path), path); }
  }
  assert.ok(data.sources.every(path => /\.(kt|java)$/.test(path) && statSync(path).isFile()));
  return { data, graph: JSON.parse(readFileSync(graph)), output };
}
const jvm = run('jvm', project, ':', 'compileKotlin');
assert.deepEqual(jvm.data.sources.map(path => path.slice(project.length + 1)).sort(), [
  'build/generated/collector/Generated.kt', 'src/main/java/JavaInput.java', 'src/main/kotlin/App.kt',
]);
assert.ok(jvm.graph.includes(':generateCollectorSource'));
for (const name of ['dep', 'leaf']) {
  assert.ok(jvm.graph.includes(`:${name}:compileJava`));
  assert.ok(jvm.data.classpath.some(path => path.startsWith(join(project, name, 'build'))));
}
assert.ok(jvm.data.classpath.some(path => /kotlin-stdlib.*\.jar$/.test(path)));
const empty = run('empty-producer', project, ':', 'compileKotlin', ['-PproducerClasspath=true']);
assert.ok(empty.graph.includes(':generateCollectorClasses'));
assert.ok(!empty.data.classpath.some(path => path.endsWith('/generated/empty-plugin-classes')));
assert.equal(empty.data.omittedClasspath.length, 1);
assert.equal(empty.data.omittedClasspath[0].producer, ':generateCollectorClasses');
assert.equal(empty.data.omittedClasspath[0].reason, 'completed-producer-without-output');
run('disabled-producer', project, ':', 'compileKotlin', ['-PproducerClasspath=true', '-PdisabledProducer=true'], /missing or unreadable/);
run('failed-producer', project, ':', 'compileKotlin', ['-PproducerClasspath=true', '-PfailedProducer=true', '--rerun-tasks'], /CLASSPATH_PRODUCER_FAILED/);
const present = run('present-producer', project, ':', 'compileKotlin', ['-PproducerClasspath=true', '-PpresentProducer=true', '--rerun-tasks']);
assert.ok(present.data.classpath.some(path => path.endsWith('/generated/empty-plugin-classes')));
assert.deepEqual(present.data.omittedClasspath, []);
run('missing-library', project, ':', 'compileKotlin', ['-PmissingLibrary=true'], /missing-library\.jar/);
run('wrong-task', project, ':', 'help', [], /KotlinCompile/);
run('missing-task', project, ':', 'notACompileTask', [], /notACompileTask/);
run('missing-module', project, ':absent', 'compileKotlin', [], /:absent/);
run('relative-output', project, ':', 'compileKotlin', ['-PkotlinEtsInputsOutput=relative.json'], /absolute/);
run('existing-output', project, ':', 'compileKotlin', [`-PkotlinEtsInputsOutput=${jvm.output}`], /exist|fresh/);
function sourceHashes(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap(entry => {
    const path = join(directory, entry.name);
    return entry.isDirectory() ? sourceHashes(path) : [{ path, sha256: createHash('sha256').update(readFileSync(path)).digest('hex') }];
  });
}
const before = sourceHashes(join(host, 'app/src'));
const android = run('android', host, ':app', 'compileDebugKotlin', ['-Pandroid.useAndroidX=true']);
assert.ok(android.data.sources.some(path => path.endsWith('/Page.kt')));
assert.ok(android.data.sources.some(path => path.endsWith('/MainActivity.kt')));
assert.ok(android.data.classpath.some(path => path.endsWith('/platforms/android-35/android.jar')));
assert.ok(android.data.classpath.some(path => /transforms\/.*\.jar$/.test(path)));
assert.deepEqual(sourceHashes(join(host, 'app/src')), before);
writeFileSync(join(work, 'complete.json'), JSON.stringify({ jvmSources: jvm.data.sources.length,
  jvmClasspath: jvm.data.classpath.length, androidSources: android.data.sources.length,
  androidClasspath: android.data.classpath.length, negatives: 8, producerCases: 4, selectedCompileTasksAbsent: true,
  androidSourcesUnchanged: true, scriptSha256: createHash('sha256').update(readFileSync(script)).digest('hex') }, null, 2));
console.log('PASS actual Gradle inputs, generated sources/classes, empty producer provenance, transitive projects, Android classpath, eight closed boundaries');
