import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
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
const promotedAccessor = join(here, '../globals/Accessor.kt');
const sources = [...['Properties.kt', 'Stored.kt', 'Consumer.kt'].map(name => join(here, name)), promotedAccessor];
const inputs = [...readdirSync(join(root, 'src'), { recursive: true }).filter(p => p.endsWith('.kt')).map(p => join(root, 'src', p)),
  ...readdirSync(here).filter(p => p.endsWith('.kt')).map(p => join(here, p)), promotedAccessor, fileURLToPath(import.meta.url)].map(path => ({ path, sha256: hash(path) }));
const result = { inputs, commands: [], passed: false, level: 'JVM/ETS host; not SDK/native' };
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
run('jvm-build', 'bash', [compiler, ...sources, join(here, 'Oracle.kt'), '-d', jar]);
result.expected = run('jvm', 'java', ['-cp', `${jar}:${cp}`, 'computed.OracleKt']).trim().split('\n');
const flat = join(work, 'Computed.ets'), modules = join(work, 'modules'), reversed = join(work, 'reversed');
run('flat', 'bash', [cli, '--mode', 'language', '--out', flat, ...sources]);
run('modules', 'bash', [cli, '--mode', 'language', '--out-dir', modules, ...sources]);
run('reversed', 'bash', [cli, '--mode', 'language', '--out-dir', reversed, ...sources.toReversed()]);
const names = readdirSync(modules).sort();
assert.deepEqual(names, readdirSync(reversed).sort());
for (const name of names) assert.equal(readFileSync(join(modules, name), 'utf8'), readFileSync(join(reversed, name), 'utf8'));
const options = { strict: true, noEmit: true, target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, types: [] };
const files = [flat, ...names.map(p => join(modules, p))];
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
  const e = load(entry), values = [e.initialSnapshot()];
  for (const value of [-3, 0, 1, 2, 5, 12]) for (const extra of [-2, 0, 3])
    values.push(e.readTwice(value), e.update(value, extra), e.setOnly(extra), e.storedAccess(value, extra));
  return values;
}
assert.equal(result.expected.length, 73);
result.actual = evaluate(flat); result.moduleActual = evaluate(join(modules, 'Consumer.ets'));
assert.deepEqual(result.actual, result.expected); assert.deepEqual(result.moduleActual, result.expected);
const parsed = ts.createSourceFile('Properties.ts', readFileSync(join(modules, 'Properties.ets'), 'utf8'), ts.ScriptTarget.Latest, true);
const setter = parsed.statements.find(n => ts.isFunctionDeclaration(n) && n.name?.text === '__etsSet_score');
assert.ok(setter); assert.deepEqual(setter.parameters.map(p => p.name.getText(parsed)), ['adjusted']);
const storage = parsed.statements.filter(ts.isVariableStatement).flatMap(n => n.declarationList.declarations.map(d => d.name.getText(parsed)));
for (const name of ['score', 'optional', 'hidden']) assert.ok(!storage.includes(name), `computed ${name} must not acquire storage`);
const stored = ts.createSourceFile('Stored.ts', readFileSync(join(modules, 'Stored.ets'), 'utf8'), ts.ScriptTarget.Latest, true);
const exported = node => node.modifiers?.some(m => m.kind === ts.SyntaxKind.ExportKeyword) ?? false;
for (const name of ['amount', 'getterOnly', 'setterOnly', 'privateAmount']) {
  const field = stored.statements.find(n => ts.isVariableStatement(n) && n.declarationList.declarations.some(d => d.name.getText(stored) === '__etsField_' + name));
  assert.ok(field, name); assert.equal(exported(field), false, name);
}
const privateSetter = stored.statements.find(n => ts.isFunctionDeclaration(n) && n.name?.text === '__etsSet_privateAmount');
assert.ok(privateSetter); assert.equal(exported(privateSetter), false);
const amountSetter = stored.statements.find(n => ts.isFunctionDeclaration(n) && n.name?.text === '__etsSet_amount');
assert.deepEqual(amountSetter.parameters.map(p => p.name.getText(stored)), ['newAmount']);
result.negatives = [];
for (const name of ['Delegated', 'Extension']) {
  const source = join(here, name + '.kt'), output = join(work, name + '.ets');
  run(name + '-jvm', 'bash', [compiler, source, '-d', join(work, name + '.jar')]);
  const diagnostic = JSON.parse(run(name, 'bash', [cli, '--mode', 'language', '--out', output, source], 2));
  assert.equal(diagnostic.code, 'UNSUPPORTED'); assert.equal(diagnostic.source.file, source);
  assert.ok(diagnostic.source.line > 0); assert.equal(existsSync(output), false); result.negatives.push(diagnostic);
}
for (const input of inputs) assert.equal(hash(input.path), input.sha256);
result.outputs = files.map(path => ({ path, sha256: hash(path) })); result.passed = true; record();
console.log('PASS 73 flat + module JVM/host property results, cross-file class access, initialization, private storage/setters, names and boundaries');
