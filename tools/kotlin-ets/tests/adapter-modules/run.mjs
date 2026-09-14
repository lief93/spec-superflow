import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, statSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../..');
mkdirSync(join(here, '.work'), { recursive: true });
assert.ok(process.argv.length === 2 || (process.argv.length === 4 && process.argv[2] === '--resume'), 'Usage: run.mjs [--resume EVIDENCE]');
const resume = process.argv[2] === '--resume';
const work = resume ? resolve(process.argv[3]) : mkdtempSync(join(here, '.work/cli-'));
console.log(`Evidence: ${work}`);
const started = new Date().toISOString();
const snapshot = join(work, 'tool');
mkdirSync(snapshot, { recursive: true });
const inputs = ['src', 'adapters', 'examples/adapters', 'kotlin-ets', 'adapter-modules.mjs', 'tests/adapter-modules/fixtures'];
const hash = path => createHash('sha256').update(readFileSync(path)).digest('hex');
const manifest = resume ? JSON.parse(readFileSync(join(work, 'snapshot.json'), 'utf8')) : [];
for (const input of resume ? [] : inputs) {
  const from = join(root, input), to = join(snapshot, input);
  cpSync(from, to, { recursive: true });
  const paths = statSync(from).isFile() ? [input]
    : readdirSync(from, { recursive: true, withFileTypes: true }).filter(entry => entry.isFile())
      .map(entry => join(entry.parentPath ?? entry.path, entry.name).slice(root.length + 1));
  for (const path of paths) manifest.push({ path, sha256: hash(join(root, path)) });
}
writeFileSync(join(work, 'snapshot.json'), JSON.stringify(manifest, null, 2));
for (const entry of manifest) {
  assert.equal(hash(join(root, entry.path)), entry.sha256, 'cannot resume changed inputs');
  assert.equal(hash(join(snapshot, entry.path)), entry.sha256, 'cannot resume changed snapshot');
}
const jdk = process.env.JAVA_HOME ?? '/Applications/Android Studio.app/Contents/jbr/Contents/Home';
const env = { ...process.env, JAVA_HOME: jdk, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC', KOTLIN_ETS_ADAPTER_DIRS: '' };
const results = [];
function run(label, command, args, overrides = {}) {
  for (const entry of manifest) assert.equal(hash(join(snapshot, entry.path)), entry.sha256, 'snapshot changed');
  const log = join(work, `${label}.json`);
  if (resume && existsSync(log)) {
    const saved = JSON.parse(readFileSync(log, 'utf8'));
    assert.equal(saved.command, command, 'cached command differs');
    assert.deepEqual(saved.args, args, 'cached arguments differ');
    results.push({ label, status: saved.status, elapsedMs: saved.elapsedMs, reused: true });
    return saved;
  }
  const start = Date.now();
  const result = spawnSync(command, args, { env: { ...env, ...overrides }, encoding: 'utf8', maxBuffer: 16 * 1024 * 1024 });
  const report = { command, args, status: result.status, elapsedMs: Date.now() - start, stdout: result.stdout, stderr: result.stderr };
  writeFileSync(join(work, `${label}.json`), JSON.stringify(report, null, 2));
  results.push({ label, status: result.status, elapsedMs: report.elapsedMs });
  if (result.error) throw result.error;
  return result;
}
function success(result) { assert.equal(result.status, 0, result.stdout + '\n' + result.stderr); }
const compilerCp = run('compiler-path', 'bash', [join(root, 'tests/stdlib/compiler.sh'), '--classpath']);
success(compilerCp);
const cp = compilerCp.stdout.trim();
const java = join(jdk, 'bin/java');
const fixtures = join(snapshot, 'tests/adapter-modules/fixtures');
const api = join(work, 'source-api.jar');
const classes = join(work, 'oracle.jar');
function compile(label, output, files) {
  const result = run(label, java, ['-cp', cp, 'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler',
    '-no-stdlib', '-no-reflect', '-classpath', `${cp}:${api}`, '-d', output, ...files]);
  success(result);
}
compile('source-library', api, [join(fixtures, 'Api.kt')]);
compile('jvm-compile', classes, ['Values.kt', 'Oracle.kt'].map(name => join(fixtures, name)));
const oracle = run('jvm-oracle', java, ['-cp', `${classes}:${api}:${cp}`, 'adapterconsumer.OracleKt']);
success(oracle);
const external = join(work, 'independent modules with spaces');
cpSync(join(snapshot, 'examples/adapters'), external, { recursive: true });
function cli(label, source, { mode = 'language', entry, adapters = '', tool = snapshot, classpath = `${api}:${cp}`, status = 0 } = {}) {
  const output = join(work, `${label}.ets`);
  const args = [join(tool, 'kotlin-ets'), '--mode', mode, '--classpath', classpath, '--out', output];
  if (entry) args.push('--entry', entry);
  args.push(join(fixtures, source));
  const result = run(label, 'bash', args, { KOTLIN_ETS_ADAPTER_DIRS: adapters });
  assert.equal(result.status, status, result.stdout + '\n' + result.stderr);
  const report = JSON.parse(result.stdout.trim().split('\n').at(-1));
  assert.equal(report.ok, status === 0);
  if (status !== 0) { assert.equal(existsSync(output), false); return report; }
  return readFileSync(output, 'utf8');
}
const values = cli('language', 'Values.kt');
assert.match(values, /Math\.abs\(value\)/);
assert.match(values, /console\.log\(/);
const transpiled = ts.transpileModule(values, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS }, reportDiagnostics: true });
assert.deepEqual(transpiled.diagnostics, []);
const printed = [];
const context = { exports: {}, console: { log: value => printed.push(String(value)) } };
vm.runInNewContext(transpiled.outputText + '\nconsole.log(magnitude(-7.5)); console.log(magnitude(3.25)); report("adapter:effect");', context, { timeout: 1000 });
assert.equal(printed.join('\n'), oracle.stdout.trim(), 'JVM / emitted value + effect parity');
const unsupported = cli('unknown-overload', 'UnknownOverload.kt', { status: 2 });
assert.equal(unsupported.code, 'UNSUPPORTED');
assert.match(unsupported.message, /exactly one Double/);
assert.equal(resolve(unsupported.source.file), join(fixtures, 'UnknownOverload.kt'));
assert.equal(readFileSync(unsupported.source.file, 'utf8').slice(unsupported.source.start, unsupported.source.end), 'absolute(value)');
const receiver = cli('unknown-receiver', 'UnknownReceiver.kt', { status: 2 });
assert.equal(receiver.code, 'UNSUPPORTED');
assert.match(receiver.message, /exactly one Double/);
assert.equal(resolve(receiver.source.file), join(fixtures, 'UnknownReceiver.kt'));
assert.equal(readFileSync(receiver.source.file, 'utf8').slice(receiver.source.start, receiver.source.end), 'absolute(value)');
const none = cli('no-extension', 'NoExtension.kt', { adapters: external });
assert.ok(!none.includes('Math') && !none.includes('Column') && !none.includes('import '));
const emptyTool = join(work, 'no-modules-tool');
mkdirSync(emptyTool, { recursive: true });
for (const path of ['src', 'kotlin-ets', 'adapter-modules.mjs']) cpSync(join(snapshot, path), join(emptyTool, path), { recursive: true });
assert.equal(cli('no-modules', 'NoExtension.kt', { tool: emptyTool }), none, 'no-extension bytes identical with/without modules');
const missing = join(work, 'missing-provider');
mkdirSync(join(missing, 'META-INF/services'), { recursive: true });
writeFileSync(join(missing, 'Unrelated.kt'), 'package missing\nclass Unrelated\n');
writeFileSync(join(missing, 'META-INF/services/dev.ets.AdapterModule'), 'missing.AbsentProvider\n');
const missingReport = cli('missing-provider', 'NoExtension.kt', { adapters: missing, status: 1 });
assert.match(missingReport.message, /Cannot load adapter module:.*missing\.AbsentProvider/);
const probe = process.env.KOTLIN_ETS_PROBE ?? '/tmp/kotlin-official-frontend-probe-06';
const composeCp = JSON.parse(readFileSync(join(probe, 'classpath.json'), 'utf8')).join(':');
const page = cli('page', 'Page.kt', { mode: 'page', entry: 'demo.adapters.AdapterPage', adapters: external, classpath: composeCp });
assert.ok(page.includes('Text("Independent adapter")'));
assert.ok(page.includes('.width(120).id("adapter-frame")'));
assert.ok(page.includes('.width(24).id("adapter-content")'));
assert.ok(!page.includes('this.Frame("Independent adapter"'), 'explicit adapter source claim precedes structural source builder');
const omitted = cli('omitted-modifier', 'OmittedModifier.kt', { mode: 'page', entry: 'demo.adapters.OmittedModifierPage',
  adapters: external, classpath: composeCp, status: 2 });
assert.equal(omitted.code, 'UNSUPPORTED');
assert.equal(omitted.message, 'Example Frame requires an explicit modifier; omitted defaults are unsupported');
assert.equal(resolve(omitted.source.file), join(fixtures, 'OmittedModifier.kt'));
assert.equal(readFileSync(omitted.source.file, 'utf8').slice(omitted.source.start, omitted.source.end), 'Frame("Title") {}');
for (const entry of manifest) assert.equal(hash(join(root, entry.path)), entry.sha256, 'live production/fixture changed during proof');
writeFileSync(join(work, 'result.json'), JSON.stringify({ passed: true, started, finished: new Date().toISOString(), resumed: resume, results, manifest,
  oracle: printed, page: { path: join(work, 'page.ets'), sha256: hash(join(work, 'page.ets')) },
  boundary: 'Public launcher, real K2 and Compose dependencies; SDK is a separate pending check. No native.' }, null, 2));
console.log(`PASS public CLI language/JVM effects, source overload rejection, no-extension bytes, SPI missing provider, external Compose adapter: ${work}`);
