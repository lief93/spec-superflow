import assert from 'node:assert/strict';
import { mkdirSync, mkdtempSync, readdirSync, readFileSync, writeFileSync, existsSync } from 'node:fs';
import { createHash } from 'node:crypto';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';
import { ts } from './runtime-assertions.mjs';

assert.equal(process.env.KOTLIN_ETS_BUILD_SLOT, '1', 'Run only in a main-approved frozen public CLI build slot');
const tests = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(tests, '../..');
const env = { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' };
mkdirSync(path.join(tests, '.build'), { recursive: true });
const run = mkdtempSync(path.join(tests, '.build/quantifiers.'));
console.log(`Quantifier public CLI evidence: ${run}`);
function command(label, executable, args, expectedStatus = 0) {
  const result = spawnSync(executable, args, { env, encoding: 'utf8', timeout: 600000 });
  writeFileSync(path.join(run, label + '.stdout'), result.stdout ?? '');
  writeFileSync(path.join(run, label + '.stderr'), result.stderr ?? '');
  writeFileSync(path.join(run, label + '.json'), JSON.stringify({ executable, args, status: result.status,
    signal: result.signal, error: result.error?.message }) + '\n');
  assert.equal(result.status, expectedStatus, `${label}: ${result.stdout}\n${result.stderr}`);
  return result.stdout;
}
const names = ['QuantifierLibrary', 'QuantifierCases', 'NullEquality'];
const fixtures = names.map(name => path.join(tests, 'fixtures/quantifiers', name + '.kt'));
const production = readdirSync(path.join(root, 'src'), { recursive: true }).filter(file => file.endsWith('.kt'))
  .sort().map(file => path.join(root, 'src', file));
const hashes = () => [...production, ...fixtures].map(file => ({ file,
  sha256: createHash('sha256').update(readFileSync(file)).digest('hex') }));
const before = hashes();
const compiler = path.join(tests, 'compiler.sh');
const jar = path.join(run, 'oracle.jar');
command('jvm-compile', 'bash', [compiler, '-d', jar, ...fixtures,
  path.join(tests, 'QuantifierOracle.kt'), path.join(tests, 'QuantifierCrossOracle.kt'), path.join(tests, 'NullEqualityOracle.kt')]);
const cp = command('classpath', 'bash', [compiler, '--classpath']).trim();
const oracle = command('jvm', 'java', ['-cp', `${cp}:${jar}`, 'quantifiercases.QuantifierOracleKt']);
const crossOracle = command('cross-jvm', 'java', ['-cp', `${cp}:${jar}`, 'quantifiercases.QuantifierCrossOracleKt']).trim().split('\n');
const nullOracle = command('null-jvm', 'java', ['-cp', `${cp}:${jar}`, 'nullequalitycases.NullEqualityOracleKt']).trim().split('\n').map(JSON.parse);
const output = path.join(run, 'modules');
command('cli', path.join(root, 'kotlin-ets'), ['--mode', 'language', '--out-dir', output, ...fixtures]);
assert.deepEqual(readdirSync(output).sort(), names.map(name => name + '.ets').sort());
const modules = new Map(names.map(name => [name, readFileSync(path.join(output, name + '.ets'), 'utf8')]));
const options = { strict: true, noEmit: true, types: [], lib: ['lib.es2020.d.ts'],
  target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS };
const host = ts.createCompilerHost(options);
const virtual = new Map([...modules].map(([name, source]) => [path.join(output, name + '.ts'), source]));
const originalExists = host.fileExists.bind(host), originalRead = host.readFile.bind(host), originalSource = host.getSourceFile.bind(host);
host.fileExists = file => virtual.has(file) || originalExists(file);
host.readFile = file => virtual.get(file) ?? originalRead(file);
host.getSourceFile = (file, version, onError, createNew) => virtual.has(file)
  ? ts.createSourceFile(file, virtual.get(file), version, true) : originalSource(file, version, onError, createNew);
const diagnostics = ts.getPreEmitDiagnostics(ts.createProgram([...virtual.keys()], options, host));
writeFileSync(path.join(run, 'typecheck.txt'), diagnostics.map(d => ts.flattenDiagnosticMessageText(d.messageText, '\n')).join('\n'));
assert.equal(diagnostics.length, 0, 'Unchanged emitted module static checking');
const context = vm.createContext({});
const cache = new Map();
function load(name) {
  name = name.replace(/^\.\//, '');
  if (cache.has(name)) return cache.get(name);
  assert.ok(modules.has(name), `Unexpected import ${name}`);
  const exports = {};
  cache.set(name, exports);
  const emitted = ts.transpileModule(modules.get(name), { compilerOptions: { ...options, noEmit: false }, reportDiagnostics: true });
  assert.deepEqual(emitted.diagnostics, []);
  context.exports = exports;
  context.require = load;
  vm.runInContext(`(function(exports, require) { ${emitted.outputText}\n})(exports, require);`, context, { timeout: 1000 });
  return exports;
}
context.cases = load('QuantifierCases');
context.library = load('QuantifierLibrary');
context.nullEquality = load('NullEquality');
const cases = oracle.trim().split('\n').map(JSON.parse);
assert.equal(cases.length, 480);
for (const test of cases) {
  context.test = test;
  const actual = vm.runInContext(`(() => {
    const values = test.input.slice(), trace = [];
    let result;
    try { result = cases.quantify(test.operation, values, test.mode, test.trigger, trace); }
    catch (error) { result = error.message.split(':')[0]; }
    return { result, trace, values };
  })()`, context, { timeout: 1000 });
  assert.deepEqual(JSON.parse(JSON.stringify(actual)), { result: test.result, trace: test.trace, values: test.values }, JSON.stringify(test));
}
const cross = vm.runInContext(`(() => {
  const log = [];
  const ordered = library.orderedAny(log);
  return [String(ordered), log.join(','), String(cases.crossFileNullable([null, 1, null])),
    String(cases.crossFileStrings(['go', 'stop', 'later'])), String(cases.crossFileStrings([])),
    String(library.listAny([-1, 2, 3], x => x > 0)), String(library.mutableAll([1, 2, 3], x => x > 0))];
})()`, context, { timeout: 1000 });
assert.deepEqual(Array.from(cross), crossOracle);
assert.equal(nullOracle.length, 30);
for (const test of nullOracle) {
  const actual = vm.runInContext(test.expression, context, { timeout: 1000 });
  assert.deepEqual(JSON.parse(JSON.stringify(actual)), test.value, test.expression);
}
const rejected = path.join(run, 'rejected.ets');
command('rejected', path.join(root, 'kotlin-ets'), ['--mode', 'language', '--out', rejected,
  path.join(tests, 'fixtures/quantifiers/QuantifierRejected.kt')], 2);
assert.equal(existsSync(rejected), false);
assert.deepEqual(hashes(), before, 'Production and same-input fixtures must stay frozen');
writeFileSync(path.join(run, 'result.json'), JSON.stringify({ passed: true, cases: cases.length,
  crossCases: crossOracle.length, nullCases: nullOracle.length, sourceHashes: before, output, typechecked: true }) + '\n');
console.log('PASS 480 quantifier cases, seven cross-file/order checks, 30 nullable/null cases, rejection and source hash guard');
