import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { homedir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';

const here = dirname(fileURLToPath(import.meta.url)), root = resolve(here, '../../..');
const models = join(root, 'tests/language/models');
mkdirSync(join(here, '.work'), { recursive: true });
const work = mkdtempSync(join(here, '.work/run-'));
console.log(`Evidence: ${work}`);
const production = readdirSync(join(root, 'src'), { recursive: true }).filter(p => p.endsWith('.kt')).map(p => join(root, 'src', p));
const sources = ['Model.kt', 'Selection.kt', 'Application.kt', 'Queries.kt'].map(p => join(models, p));
const page = join(here, 'ModelPage.kt'), probe = join(here, 'ModelUiProbe.kt'), oracle = join(models, 'Oracle.kt');
const hash = path => createHash('sha256').update(readFileSync(path)).digest('hex');
const inputs = [...production, ...sources, page, probe, oracle, fileURLToPath(import.meta.url)].map(path => ({ path, sha256: hash(path) }));
const result = { inputs, commands: [], passed: false, level: 'typed UI and JVM/host callback replay; not SDK/native rendering' };
const record = () => writeFileSync(join(work, 'result.json'), JSON.stringify(result, null, 2));
function run(label, command, args) {
  const r = spawnSync(command, args, { encoding: 'utf8', timeout: 600000, maxBuffer: 16 * 1024 * 1024,
    env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' } });
  for (const stream of ['stdout', 'stderr']) writeFileSync(join(work, `${label}.${stream}`), r[stream] ?? '');
  result.commands.push({ label, command, args, status: r.status }); record();
  assert.equal(r.error, undefined); assert.equal(r.status, 0, r.stdout + r.stderr); return r.stdout;
}
const compiler = join(root, 'tests/stdlib/compiler.sh');
const cp = run('classpath', 'bash', [compiler, '--classpath']).trim();
const uiCp = JSON.parse(readFileSync(join(process.env.KOTLIN_ETS_PROBE ?? '/tmp/kotlin-official-frontend-probe-06', 'classpath.json'))).join(':');
const plugins = join(homedir(), '.gradle/caches/modules-2/files-2.1/org.jetbrains.kotlin/kotlin-compose-compiler-plugin-embeddable/2.1.20');
const plugin = readdirSync(plugins).map(p => join(plugins, p, 'kotlin-compose-compiler-plugin-embeddable-2.1.20.jar')).find(existsSync);
assert.ok(plugin, 'installed official Compose compiler plugin');
const jvmJar = join(work, 'source.jar');
run('source-jvm-build', 'bash', [compiler, '-classpath', uiCp, `-Xplugin=${plugin}`, ...sources, page, oracle, '-d', jvmJar]);
result.expected = run('oracle', 'java', ['-cp', `${jvmJar}:${cp}:${uiCp}`, 'models.OracleKt']).trim().split('\n');
const probeJar = join(work, 'probe.jar'), output = join(work, 'ui');
run('probe-build', 'bash', [compiler, ...production, probe, '-d', probeJar]);
run('probe', 'java', ['-cp', `${probeJar}:${cp}`, 'dev.ets.ModelUiProbeKt', uiCp, output, ...sources, page]);
const classpathFile = join(work, 'classpath.txt');
writeFileSync(classpathFile, uiCp.split(':').join('\n'));
const publicOutput = join(work, 'public');
run('public-cli', 'bash', [join(root, 'kotlin-ets'), '--mode', 'page', '--entry', 'models.ui.ModelPage',
  '--classpath-file', classpathFile, '--out-dir', publicOutput, ...sources, page]);
const names = readdirSync(publicOutput).filter(p => p.endsWith('.ets')).sort();
assert.deepEqual(names, readdirSync(output).filter(p => p.endsWith('.ets')).sort());
for (const name of names) assert.equal(readFileSync(join(publicOutput, name), 'utf8'), readFileSync(join(output, name), 'utf8'));
const host = join(output, 'host'), cache = new Map();
const options = { strict: true, noEmit: true, target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, types: [] };
const typed = readdirSync(host).map(name => { const path = join(host, name.replace(/\.ets$/, '.ts')); writeFileSync(path, readFileSync(join(host, name))); return path; });
assert.deepEqual(ts.getPreEmitDiagnostics(ts.createProgram(typed, options)).map(d => ts.flattenDiagnosticMessageText(d.messageText, '\n')), []);
function load(path) {
  if (cache.has(path)) return cache.get(path);
  const exports = {}; cache.set(path, exports);
  const code = ts.transpileModule(readFileSync(path, 'utf8'), { compilerOptions: options }).outputText;
  vm.runInNewContext(code, { exports, require: name => load(resolve(dirname(path), name + '.ets')) }, { timeout: 1000 });
  return exports;
}
const app = load(join(host, 'Application.ets')), selection = load(join(host, 'Selection.ets'));
const queries = load(join(host, 'Queries.ets')), ui = load(join(host, 'ModelPage.ets'));
result.actual = [queries.emptinessCheck(false), queries.emptinessCheck(true), queries.evaluationOrder(),
  queries.nullableLet(null), queries.nullableLet(''), queries.nullableLet('Title'),
  queries.guardedGeneric(null), queries.guardedGeneric('Title'), queries.nullableGeneric(null), queries.nullableGeneric('Title')];
for (const minimum of [-1, 0, 2, 3, 7]) for (const extra of [-2, 0, 3]) for (const pick of [false, true]) {
  result.actual.push(app.scenario(minimum, extra, pick));
  ui.click();
  result.actual.push(selection.selectedLabel() + ':' + selection.selectedCount());
}
assert.equal(result.expected.length, 70); assert.deepEqual(result.actual, result.expected);
for (const input of inputs) assert.equal(hash(input.path), input.sha256);
result.outputs = names.map(name => ({ path: join(publicOutput, name), sha256: hash(join(publicOutput, name)) }));
result.passed = true; record();
console.log('PASS typed Compose values/conditions, public CLI parity and 70 JVM/host results with actual UI callback replay; no native rendering');
