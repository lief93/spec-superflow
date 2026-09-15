import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { compilerEnvironment } from '../../../compiler-environment.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../../..');
const host = process.env.COLLECTOR_ANDROID_HOST || '/private/tmp/kotlin-ets-native-20260914-06/android';
mkdirSync(join(here, '.work'), { recursive: true });
const work = mkdtempSync(join(here, '.work/run-'));
console.log(`Evidence: ${work}`);
const project = join(work, 'plugin project');
cpSync(join(here, 'fixture'), project, { recursive: true });
cpSync(join(host, 'gradlew'), join(project, 'gradlew'));
cpSync(join(host, 'gradle'), join(project, 'gradle'), { recursive: true });
const hash = path => createHash('sha256').update(readFileSync(path)).digest('hex');
const unchangedPaths = [join(project, 'build.gradle'), join(project, 'settings.gradle'), join(project, 'src/main/kotlin/Model.kt'),
  ...readdirSync(join(root, 'src'), { recursive: true }).filter(p => p.endsWith('.kt')).map(p => join(root, 'src', p)),
  join(root, 'project.mjs'), join(root, 'project-inputs.gradle'), join(root, 'compiler-environment.mjs')];
const hashes = unchangedPaths.map(path => ({ path, sha256: hash(path) }));
const javaHome = process.env.JAVA_HOME || '/Applications/Android Studio.app/Contents/jbr/Contents/Home';
const env = { ...process.env, JAVA_HOME: javaHome, PATH: `${javaHome}/bin:${process.env.PATH}`,
  JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' };
function run(label, command, args) {
  const result = spawnSync(command, args, { cwd: project, env, encoding: 'utf8', timeout: 600000, maxBuffer: 16 * 1024 * 1024 });
  writeFileSync(join(work, `${label}.json`), JSON.stringify({ command, args, status: result.status, error: result.error?.message }, null, 2));
  for (const stream of ['stdout', 'stderr']) writeFileSync(join(work, `${label}.${stream}`), result[stream] || '');
  assert.equal(result.error, undefined);
  return result;
}
const oracle = run('gradle-compile', 'bash', [join(project, 'gradlew'), '--offline', '--no-daemon', '--console=plain', 'compileKotlin']);
assert.equal(oracle.status, 0, oracle.stdout + oracle.stderr);
const evidence = join(work, 'collection');
const collect = run('collect', 'bash', [join(root, 'kotlin-ets'), '--project', project, '--module', ':',
  '--compile-task', 'compileKotlin', '--collect-only', '--offline', '--work-dir', evidence]);
assert.equal(collect.status, 0, collect.stdout + collect.stderr);
const inputs = JSON.parse(readFileSync(join(evidence, 'inputs.json')));
assert.ok(inputs.compilerArguments?.some(arg => arg.includes('kotlin-serialization-compiler-plugin-embeddable-2.1.20.jar')),
  'Collect actual serialization compiler plugin, not only source/classpath');
assert.equal(inputs.compilerVersion, '2.1.20');
const environment = compilerEnvironment(inputs);
assert.ok(environment.arguments.includes('plugin:org.jetbrains.kotlinx.serialization:disableIntrinsic=true'));
assert.ok(environment.arguments.includes('-opt-in=kotlinx.serialization.InternalSerializationApi'));
const extra = join(work, 'frontend-arguments.txt');
writeFileSync(extra, environment.arguments.join('\n') + '\n');
const empty = join(work, 'no-plugin.txt'); writeFileSync(empty, '-jvm-target\n17\n');
const cp = run('compiler-classpath', 'bash', [join(root, 'tests/stdlib/compiler.sh'), '--classpath']).stdout.trim();
const tool = join(work, 'probe.jar');
const compilerSources = readdirSync(join(root, 'src'), { recursive: true }).filter(p => p.endsWith('.kt')).map(p => join(root, 'src', p));
const build = run('build-probe', 'java', ['-Xmx3g', '-cp', cp, 'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler',
  '-no-stdlib', '-no-reflect', '-classpath', cp, '-d', tool, ...compilerSources, join(here, 'FrontendProbe.kt')]);
assert.equal(build.status, 0, build.stderr);
const probe = file => run(file === empty ? 'without-plugin' : 'with-plugin', 'java', ['-Xmx3g', '-cp', cp + ':' + tool,
  'dev.ets.FrontendProbeKt', file, join(evidence, 'classpath.txt'), join(evidence, 'sources.txt')]);
const without = probe(empty);
assert.notEqual(without.status, 0);
assert.match(without.stderr, /descriptor|does not implement/);
const withPlugin = probe(extra);
assert.equal(withPlugin.status, 0, withPlugin.stdout + withPlugin.stderr);
assert.match(withPlugin.stdout, /serialization-generated descriptor IR/);
const output = join(work, 'not-yet-supported.ets');
const publicRun = run('public-project', 'bash', [join(root, 'kotlin-ets'), '--project', project, '--module', ':',
  '--compile-task', 'compileKotlin', '--mode', 'language', '--out', output, '--offline', '--work-dir', join(work, 'public')]);
assert.equal(publicRun.status, 2, publicRun.stdout + publicRun.stderr);
const diagnostic = JSON.parse(publicRun.stdout);
assert.equal(diagnostic.code, 'UNSUPPORTED');
assert.match(diagnostic.message, /Only source class and interface heritage is supported/);
assert.ok(diagnostic.source, 'Backend limitation has a source, not a generic Kotlin resolution failure');
assert.equal(existsSync(output), false);
for (const input of hashes) assert.equal(hash(input.path), input.sha256, `Input changed during acceptance: ${input.path}`);
writeFileSync(join(work, 'result.json'), JSON.stringify({ passed: true, environment,
  inputs: hashes,
  frontend: 'original Gradle success; missing plugin fails; captured plugin generates typed IR',
  backend: diagnostic, nativeExecution: false }, null, 2));
console.log('PASS real Gradle serialization -> frontend generated IR; public backend limitation remains explicit');
