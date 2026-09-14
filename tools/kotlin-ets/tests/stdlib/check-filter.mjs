import assert from 'node:assert/strict';
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';
import { assertRuntimeHelpers, ts } from './runtime-assertions.mjs';

const tests = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(tests, '../..');
mkdirSync(path.join(tests, '.build'), { recursive: true });
const run = mkdtempSync(path.join(tests, '.build/filter.'));
console.log(`Filter evidence: ${run}`);
function command(name, executable, args, expected = 0) {
  const result = spawnSync(executable, args, { encoding: 'utf8', timeout: 180000 });
  writeFileSync(path.join(run, `${name}.stdout`), result.stdout ?? '');
  writeFileSync(path.join(run, `${name}.stderr`), result.stderr ?? '');
  writeFileSync(path.join(run, `${name}.json`), JSON.stringify({ executable, args,
    status: result.status, signal: result.signal, error: result.error?.message }, null, 2) + '\n');
  assert.equal(result.status, expected, `${name}: ${result.stdout}\n${result.stderr}`);
  return result.stdout;
}
const fixture = path.join(tests, 'fixtures/Filter.kt');
const jar = path.join(run, 'oracle.jar');
command('jvm-compile', 'bash', [path.join(tests, 'compiler.sh'), '-d', jar,
  fixture, path.join(tests, 'FilterOracle.kt')]);
const cp = command('classpath', 'bash', [path.join(tests, 'compiler.sh'), '--classpath']).trim();
const oracle = command('jvm', 'java', ['-cp', `${cp}:${jar}`, 'filtercases.FilterOracleKt']);
const output = path.join(run, 'filter.ets');
command('cli', path.join(root, 'kotlin-ets'), ['--mode', 'language', '--out', output, fixture]);
const text = assertRuntimeHelpers(output, ['__etsIntDiv', '__etsListGet', '__etsListAdd', '__etsListFilter']);
const emitted = ts.transpileModule(text, { compilerOptions: {
  target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS,
}, reportDiagnostics: true });
assert.deepEqual(emitted.diagnostics, []);
const context = vm.createContext({ exports: {} });
vm.runInContext(emitted.outputText, context, { timeout: 10000 });
const cases = oracle.trim().split('\n').map(line => JSON.parse(line));
assert.equal(cases.length, 34);
for (const test of cases) {
  const actual = vm.runInContext(test.expression, context, { timeout: 10000 });
  assert.deepEqual(JSON.parse(JSON.stringify(actual)), test.value, test.expression);
}
for (const operation of ['selected', 'rejected']) {
  const input = [{ value: 1 }, null, { value: 2 }];
  for (const keep of [true, false]) {
    const result = context.exports[operation](input, () => keep);
    assert.notEqual(result, input, 'even all-true/all-false results must be fresh');
    assert.deepEqual(input, [{ value: 1 }, null, { value: 2 }], 'source unchanged');
    if (result.length) assert.equal(result[0], input[0], 'element identity preserved');
    result.push({ value: 9 });
    assert.equal(input.length, 3, 'result must not alias the source');
  }
}
writeFileSync(path.join(run, 'result.json'), JSON.stringify({ passed: true, cases: cases.length }) + '\n');
console.log(`PASS: ${cases.length} same-input JVM/public-CLI filter cases`);
