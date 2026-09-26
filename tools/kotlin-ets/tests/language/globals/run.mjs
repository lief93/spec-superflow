import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdirSync, mkdtempSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';

const here = dirname(fileURLToPath(import.meta.url)), root = resolve(here, '../../..');
mkdirSync(join(here, '.work'), { recursive: true });
const work = mkdtempSync(join(here, '.work/run-'));
console.log(`Evidence: ${work}`);
const hash = path => createHash('sha256').update(readFileSync(path)).digest('hex');
const sources = ['State.kt', 'Application.kt'].map(p => join(here, p));
const uiSources = ['UiState.kt', 'UiPage.kt'].map(p => join(here, p));
const inputs = [...readdirSync(join(root, 'src'), { recursive: true }).filter(p => p.endsWith('.kt')).map(p => join(root, 'src', p)),
  ...sources, ...uiSources, join(here, 'GlobalUiProbe.kt'), join(here, 'Oracle.kt'), fileURLToPath(import.meta.url)].map(path => ({ path, sha256: hash(path) }));
const result = { inputs, commands: [], passed: false, level: 'JVM/ETS host; not SDK or native' };
const record = () => writeFileSync(join(work, 'result.json'), JSON.stringify(result, null, 2));
function run(label, command, args, status = 0) {
  const r = spawnSync(command, args, { encoding: 'utf8', timeout: 600000, maxBuffer: 16 * 1024 * 1024,
    env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' } });
  for (const stream of ['stdout', 'stderr']) writeFileSync(join(work, `${label}.${stream}`), r[stream] ?? '');
  result.commands.push({ label, command, args, status: r.status }); record();
  assert.equal(r.error, undefined); assert.equal(r.status, status, r.stdout + r.stderr); return r.stdout;
}
const compiler = join(root, 'tests/stdlib/compiler.sh'), cli = join(root, 'kotlin-ets');
const cp = run('classpath', 'bash', [compiler, '--classpath']).trim(), jar = join(work, 'oracle.jar');
const uiJar = join(work, 'ui-probe.jar'), uiOutput = join(work, 'ui');
const uiCp = JSON.parse(readFileSync('/tmp/kotlin-official-frontend-probe-06/classpath.json')).join(':');
run('ui-probe-build', 'bash', [compiler, ...inputs.filter(x => x.path.startsWith(join(root, 'src'))).map(x => x.path), join(here, 'GlobalUiProbe.kt'), '-d', uiJar]);
run('ui-probe', 'java', ['-cp', `${uiJar}:${cp}`, 'dev.ets.GlobalUiProbeKt', uiCp, uiOutput, ...uiSources]);
const uiHost = join(uiOutput, 'host'), uiCache = new Map();
function loadUi(path) {
  if (uiCache.has(path)) return uiCache.get(path);
  const exports = {}; uiCache.set(path, exports);
  const code = ts.transpileModule(readFileSync(path, 'utf8'), { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } }).outputText;
  vm.runInNewContext(code, { exports, require: name => loadUi(resolve(dirname(path), name + '.ets')) }, { timeout: 1000 });
  return exports;
}
const uiState = loadUi(join(uiHost, 'UiState.ets'));
assert.equal(uiState.counter, 0);
uiState.click(); assert.equal(uiState.counter, 1);
uiState.click(); assert.equal(uiState.counter, 2);
result.relocatedCallback = { actualCounter: uiState.counter, level: 'actual typed callback replay; not ArkUI rendering' };
run('jvm-build', 'bash', [compiler, ...sources, join(here, 'Oracle.kt'), '-d', jar]);
result.expected = run('jvm', 'java', ['-cp', `${jar}:${cp}`, 'globals.OracleKt']).trim().split('\n');
const flat = join(work, 'Globals.ets'), modules = join(work, 'modules'), reversed = join(work, 'reversed');
run('flat', 'bash', [cli, '--mode', 'language', '--out', flat, ...sources]);
run('modules', 'bash', [cli, '--mode', 'language', '--out-dir', modules, ...sources]);
run('reversed', 'bash', [cli, '--mode', 'language', '--out-dir', reversed, ...sources.toReversed()]);
const modulePaths = readdirSync(modules).sort().map(p => join(modules, p));
for (const path of readdirSync(modules)) assert.equal(readFileSync(join(modules, path), 'utf8'), readFileSync(join(reversed, path), 'utf8'));
const options = { strict: true, noEmit: true, target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, types: [] };
const files = [flat, ...modulePaths, ...readdirSync(uiHost).map(p => join(uiHost, p))];
const typed = files.map(path => { const target = path.replace(/\.ets$/, '.ts'); writeFileSync(target, readFileSync(path)); return target; });
assert.deepEqual(ts.getPreEmitDiagnostics(ts.createProgram(typed, options)).map(d => ts.flattenDiagnosticMessageText(d.messageText, '\n')), []);
function evaluate(entry) {
  const cache = new Map();
  function load(path) {
    if (cache.has(path)) return cache.get(path);
    const exports = {}; cache.set(path, exports);
    const code = ts.transpileModule(readFileSync(path, 'utf8'), { compilerOptions: options }).outputText;
    vm.runInNewContext(code, { exports, require: name => load(resolve(dirname(path), name + '.ets')) }, { timeout: 1000 });
    return exports;
  }
  const e = load(entry), state = entry === flat ? e : load(join(modules, 'State.ets')), values = [];
  for (let round = 0; round < 2; round++) {
    state.reset(); values.push(e.snapshot(), String(e.spacing()));
    for (const step of [1, 1, 2, -1, 7]) values.push(e.advance(4, step), e.snapshot());
    e.clearSelection(); values.push(e.snapshot());
  }
  return values;
}
result.actual = evaluate(flat); result.moduleActual = evaluate(join(modules, 'Application.ets'));
assert.deepEqual(result.actual, result.expected); assert.deepEqual(result.moduleActual, result.expected);
const state = ts.createSourceFile('State.ts', readFileSync(join(modules, 'State.ets'), 'utf8'), ts.ScriptTarget.Latest, true);
const bindings = state.statements.filter(ts.isVariableStatement).flatMap(s => s.declarationList.declarations.map(d => d.name.getText(state)));
for (const name of ['baseGap', 'caption', 'currentPage', 'selection', 'visits', 'revision']) assert.ok(bindings.includes(name), name);
const isExported = node => node.modifiers?.some(m => m.kind === ts.SyntaxKind.ExportKeyword) ?? false;
const privateStorage = state.statements.find(s => ts.isVariableStatement(s) && s.declarationList.declarations.some(d => d.name.getText(state) === 'visits'));
assert.equal(isExported(privateStorage), false);
assert.ok(!state.statements.some(s => ts.isFunctionDeclaration(s) && ['__etsSet_revision', '__etsSet_visits'].includes(s.name?.text)));
// Initialized.kt is exercised positively by ../initialization/run.mjs.
for (const input of inputs) assert.equal(hash(input.path), input.sha256);
result.modules = files.map(path => ({ path, sha256: hash(path) })); result.passed = true; record();
console.log(`PASS ${result.actual.length} flat + module JVM/host global-state results, relocated Compose callback replay, names and deterministic imports; SDK/native not run`);
