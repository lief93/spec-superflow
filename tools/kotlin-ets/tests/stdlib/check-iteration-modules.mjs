import assert from 'node:assert/strict';
import { mkdirSync, mkdtempSync, readdirSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';
import { createHash } from 'node:crypto';
import { ts } from './runtime-assertions.mjs';

const tests = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(tests, '../..');
const env = { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' };
mkdirSync(path.join(tests, '.build'), { recursive: true });
const run = mkdtempSync(path.join(tests, '.build/iteration-modules.'));
console.log(`Cross-file iteration evidence: ${run}`);
function command(name, executable, args) {
  const result = spawnSync(executable, args, { env, encoding: 'utf8', timeout: 300000 });
  writeFileSync(path.join(run, `${name}.stdout`), result.stdout ?? '');
  writeFileSync(path.join(run, `${name}.stderr`), result.stderr ?? '');
  assert.equal(result.status, 0, `${name}: ${result.stdout}\n${result.stderr}`);
  return result.stdout;
}
const names = ['IteratorProducer', 'IteratorConsumer', 'IteratorBridge'];
const sources = names.map(name => path.join(tests, 'fixtures/iteration-modules', name + '.kt'));
const hashes = () => sources.map(file => createHash('sha256').update(readFileSync(file)).digest('hex'));
const sourceHashes = hashes();
const jar = path.join(run, 'oracle.jar');
command('jvm-compile', 'bash', [path.join(tests, 'compiler.sh'), '-d', jar, ...sources,
  path.join(tests, 'IterationModuleOracle.kt')]);
const cp = command('classpath', 'bash', [path.join(tests, 'compiler.sh'), '--classpath']).trim();
const expected = command('jvm', 'java', ['-cp', `${cp}:${jar}`, 'iterationmodules.IterationModuleOracleKt']).trim().split('\n');
const output = path.join(run, 'modules');
command('cli', path.join(root, 'kotlin-ets'), ['--mode', 'language', '--out-dir', output, ...sources]);
assert.deepEqual(readdirSync(output).sort(), names.map(name => name + '.ets').sort());
const modules = new Map(names.map(name => [name, readFileSync(path.join(output, name + '.ets'), 'utf8')]));
// Type-check the actual emitted module text without rewriting its private/public fields or imports.
const options = { strict: true, noEmit: true, types: [], lib: ['lib.es2020.d.ts'],
  target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS };
const host = ts.createCompilerHost(options);
const virtual = new Map([...modules].map(([name, text]) => [path.join(output, name + '.ts'), text]));
const originalExists = host.fileExists.bind(host), originalRead = host.readFile.bind(host);
host.fileExists = file => virtual.has(file) || originalExists(file);
host.readFile = file => virtual.get(file) ?? originalRead(file);
const originalSource = host.getSourceFile.bind(host);
host.getSourceFile = (file, version, onError, createNew) => virtual.has(file)
  ? ts.createSourceFile(file, virtual.get(file), version, true) : originalSource(file, version, onError, createNew);
const program = ts.createProgram([...virtual.keys()], options, host);
const diagnostics = ts.getPreEmitDiagnostics(program);
writeFileSync(path.join(run, 'typecheck.txt'), diagnostics.map(d => ts.flattenDiagnosticMessageText(d.messageText, '\n')).join('\n'));
assert.equal(diagnostics.length, 0, 'Generated cross-file cursor types must be compatible');
const readonlyProbe = path.join(output, 'ReadonlyProbe.ts');
virtual.set(readonlyProbe, `import { produce } from './IteratorProducer';
const iterator = produce([1]);
iterator.more = () => false;
iterator.take = () => 0;
`);
const readonlyDiagnostics = ts.getPreEmitDiagnostics(ts.createProgram([...virtual.keys()], options, host));
assert.deepEqual(readonlyDiagnostics.map(d => d.code), [2540, 2540], 'Both callbacks must be readonly');
virtual.delete(readonlyProbe);
const cache = new Map();
function load(name) {
  name = name.replace(/^\.\//, '');
  if (cache.has(name)) return cache.get(name);
  assert.ok(modules.has(name), `Unexpected import: ${name}`);
  const exports = {};
  cache.set(name, exports);
  const code = ts.transpileModule(modules.get(name), { compilerOptions: { ...options, noEmit: false } }).outputText;
  vm.runInNewContext(code, { exports, require: load }, { timeout: 1000 });
  return exports;
}
const m = load('IteratorBridge');
const actual = [m.transfer(4, 7), m.continuedCursor(), m.nullableTransfer(null), m.nullableTransfer(9),
  m.rangeTransfer(-2147483648, 2147483647)].map(String);
assert.deepEqual(actual, expected);
assert.deepEqual(hashes(), sourceHashes, 'JVM and CLI must compile unchanged same inputs');
writeFileSync(path.join(run, 'result.json'), JSON.stringify({ passed: true, cases: actual.length,
  modules: names, sourceHashes, actual, expected, typechecked: true, readonlyCallbacks: true }) + '\n');
console.log('PASS cross-file iterator return/parameter types, shared cursor state, JVM parity, and static TypeScript check');
