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
const implementation = readdirSync(join(root, 'src'), { recursive: true }).filter(p => p.endsWith('.kt')).sort().map(p => join(root, 'src', p));
const sources = [join(here, 'Composition.kt')];
const result = { passed: false, inputs: [...implementation, ...sources, join(here, 'Oracle.kt'), join(here, 'Probe.kt'), fileURLToPath(import.meta.url)]
  .map(path => ({ path, sha256: hash(path) })), commands: [] };
const record = () => writeFileSync(join(work, 'result.json'), JSON.stringify(result, null, 2));
function run(label, command, args) {
  const r = spawnSync(command, args, { encoding: 'utf8', timeout: 600000, maxBuffer: 32 * 1024 * 1024,
    env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' } });
  for (const stream of ['stdout', 'stderr']) writeFileSync(join(work, `${label}.${stream}`), r[stream] ?? '');
  result.commands.push({ label, command, args, status: r.status }); record();
  assert.equal(r.error, undefined); assert.equal(r.status, 0, r.stdout + r.stderr); return r.stdout;
}
const compiler = join(root, 'tests/stdlib/compiler.sh'), cli = join(root, 'kotlin-ets');
const cp = run('classpath', 'bash', [compiler, '--classpath']).trim(), oracle = join(work, 'oracle.jar');
run('jvm-build', 'bash', [compiler, ...sources, join(here, 'Oracle.kt'), '-d', oracle]);
result.expected = run('jvm-run', 'java', ['-cp', `${oracle}:${cp}`, 'declarationcomposition.OracleKt']).trimEnd().split('\n');
assert.equal(result.expected.length, 30);
const flat = join(work, 'Composition.ets'), modules = join(work, 'modules');
run('flat', 'bash', [cli, '--mode', 'language', '--out', flat, ...sources]);
run('modules', 'bash', [cli, '--mode', 'language', '--out-dir', modules, ...sources]);
assert.deepEqual(readdirSync(modules), ['Composition.ets']);
result.modules = [{ name: 'Composition.ets', path: join(modules, 'Composition.ets'), sha256: hash(join(modules, 'Composition.ets')) }];
const files = [flat, result.modules[0].path];
const options = { strict: true, noEmit: true, target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, skipLibCheck: true };
const tsFiles = files.map(path => { const target = path.replace(/\.ets$/, '.ts'); writeFileSync(target, readFileSync(path)); return target; });
assert.deepEqual(ts.getPreEmitDiagnostics(ts.createProgram(tsFiles, options)).map(d => ts.flattenDiagnosticMessageText(d.messageText, '\n')), []);
const methods = ['inlineCapture', 'localCapture', 'substitutedCapture', 'nestedCapture', 'inputCapture', 'boundCapture'];
function evaluate(path) {
  const tree = ts.createSourceFile(path, readFileSync(path, 'utf8'), ts.ScriptTarget.Latest, true);
  for (const name of methods) {
    const declaration = tree.statements.find(n => ts.isFunctionDeclaration(n) && n.name?.text === name);
    assert.ok(declaration, name);
    assert.deepEqual(declaration.parameters.map(p => p.name.getText(tree)), ['seed']);
  }
  const exports = {}, context = vm.createContext({ exports });
  vm.runInContext(ts.transpileModule(readFileSync(path, 'utf8'), { compilerOptions: options }).outputText, context, { timeout: 1000 });
  return [0, -3, 7, -2147483648, 2147483647].flatMap(seed => methods.map(name =>
    String(vm.runInContext(`exports.${name}(${seed})`, context, { timeout: 1000 }))));
}
result.actual = evaluate(flat); result.moduleActual = evaluate(result.modules[0].path);
assert.deepEqual(result.actual, result.expected); assert.deepEqual(result.moduleActual, result.expected);
const proof = join(work, 'probe.jar');
run('probe-build', 'bash', [compiler, ...implementation, join(here, 'Probe.kt'), '-d', proof]);
result.ir = run('probe', 'java', ['-cp', `${proof}:${cp}`, 'dev.ets.composition.ProbeKt', cp, ...sources]);
for (const input of result.inputs) assert.equal(hash(input.path), input.sha256);
result.output = { path: flat, sha256: hash(flat) }; result.passed = true; record();
console.log('PASS 30 flat + 30 module JVM/host results, source names and official inline capture binding; SDK/native not run');
