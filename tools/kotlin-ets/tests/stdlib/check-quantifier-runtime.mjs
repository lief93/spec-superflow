import assert from 'node:assert/strict';
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';
import { ts, assertRuntimeHelpers } from './runtime-assertions.mjs';

const tests = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(tests, '../..');
const env = { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' };
mkdirSync(path.join(tests, '.build'), { recursive: true });
const run = mkdtempSync(path.join(tests, '.build/quantifier-runtime.'));
console.log(`Quantifier isolated runtime evidence: ${run}`);
function command(label, executable, args) {
  const result = spawnSync(executable, args, { env, encoding: 'utf8', timeout: 300000 });
  writeFileSync(path.join(run, label + '.stdout'), result.stdout ?? '');
  writeFileSync(path.join(run, label + '.stderr'), result.stderr ?? '');
  assert.equal(result.status, 0, `${label}: ${result.stdout}\n${result.stderr}`);
  return result.stdout;
}
const compiler = path.join(tests, 'compiler.sh');
const cp = command('classpath', 'bash', [compiler, '--classpath']).trim();
const fixtures = ['QuantifierLibrary', 'QuantifierCases'].map(name => path.join(tests, 'fixtures/quantifiers', name + '.kt'));
const oracleJar = path.join(run, 'oracle.jar');
command('oracle-compile', 'bash', [compiler, '-d', oracleJar, ...fixtures, path.join(tests, 'QuantifierOracle.kt')]);
const oracle = command('oracle', 'java', ['-cp', `${cp}:${oracleJar}`, 'quantifiercases.QuantifierOracleKt']);
const runtimeJar = path.join(run, 'runtime.jar');
command('runtime-compile', 'bash', [compiler, '-d', runtimeJar,
  ...['target/Tree.kt', 'target/Traversal.kt', 'stdlib/StandardLibrarySupport.kt', 'stdlib/StandardLibraryDependencies.kt']
    .map(file => path.join(root, 'src', file)), path.join(tests, 'QuantifierRuntime.kt')]);
const source = command('runtime', 'java', ['-cp', `${cp}:${runtimeJar}`, 'dev.ets.tests.stdlib.QuantifierRuntimeKt']);
const file = path.join(run, 'runtime.ets');
writeFileSync(file, source);
assertRuntimeHelpers(file, ['__etsArrayIterator', '__etsListAny', '__etsListCount']);
const emitted = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2020 }, reportDiagnostics: true });
assert.deepEqual(emitted.diagnostics, []);
const context = vm.createContext({});
vm.runInContext(emitted.outputText, context, { timeout: 1000 });
const cases = oracle.trim().split('\n').map(JSON.parse);
assert.equal(cases.length, 480);
for (const test of cases) {
  context.test = test;
  const actual = vm.runInContext(`(() => {
    const values = test.input.slice(), trace = [];
    const predicate = value => {
      trace.push(value === null ? -99 : value);
      if (test.mode === 3 && trace.length === test.trigger) throw new Error('IndexOutOfBoundsException');
      if (test.mode === 4 && trace.length === test.trigger) values.push(7);
      return test.mode === 1 ? true : test.mode === 2 ? false : value !== null && value > 0;
    };
    let result;
    try {
      result = String(test.operation === 3 ? __etsListCount(values, predicate) :
        test.operation === 0 ? __etsListAny(values, predicate, true) :
        !__etsListAny(values, predicate, test.operation !== 1));
    } catch (error) { result = error.message; }
    return { result, trace, values };
  })()`, context, { timeout: 1000 });
  assert.deepEqual(JSON.parse(JSON.stringify(actual)), { result: test.result, trace: test.trace, values: test.values }, JSON.stringify(test));
}
writeFileSync(path.join(run, 'result.json'), JSON.stringify({ passed: true, cases: cases.length,
  level: 'isolated runtime versus JVM, not public CLI' }) + '\n');
console.log(`PASS ${cases.length} isolated runtime/JVM quantifier cases`);
