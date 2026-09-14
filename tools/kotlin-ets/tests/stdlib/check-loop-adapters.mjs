import assert from 'node:assert/strict';
import { mkdirSync, mkdtempSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';
import { assertRuntimeHelpers, ts } from './runtime-assertions.mjs';

const tests = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(tests, '../..');
mkdirSync(path.join(tests, '.build'), { recursive: true });
const run = mkdtempSync(path.join(tests, '.build/loop-adapters.'));
console.log(`Loop adapter evidence: ${run}`);
function command(name, executable, args) {
  const result = spawnSync(executable, args, { encoding: 'utf8', timeout: 300000 });
  writeFileSync(path.join(run, `${name}.stdout`), result.stdout ?? '');
  writeFileSync(path.join(run, `${name}.stderr`), result.stderr ?? '');
  writeFileSync(path.join(run, `${name}.json`), JSON.stringify({ executable, args,
    status: result.status, signal: result.signal, error: result.error?.message }, null, 2) + '\n');
  assert.equal(result.status, 0, `${name}: ${result.stdout}\n${result.stderr}`);
  return result.stdout;
}
const fixture = path.join(tests, 'fixtures/LoopAdapters.kt');
const jar = path.join(run, 'oracle.jar');
command('jvm-compile', 'bash', [path.join(tests, 'compiler.sh'), '-d', jar,
  fixture, path.join(tests, 'LoopAdapterOracle.kt')]);
const cp = command('classpath', 'bash', [path.join(tests, 'compiler.sh'), '--classpath']).trim();
const oracle = command('jvm', 'java', ['-cp', `${cp}:${jar}`, 'loopadaptercases.LoopAdapterOracleKt']);
const output = path.join(run, 'loops.ets');
command('cli', path.join(root, 'kotlin-ets'), ['--mode', 'language', '--out', output, fixture]);
const text = assertRuntimeHelpers(output, ['__etsIllegalArgumentException', '__etsProgressionLastElement']);
const emitted = ts.transpileModule(text, { compilerOptions: {
  target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS,
}, reportDiagnostics: true });
assert.deepEqual(emitted.diagnostics, []);
const context = vm.createContext({ exports: {} });
vm.runInContext(emitted.outputText, context, { timeout: 10000 });
const cases = oracle.trim().split('\n').map(line => JSON.parse(line));
assert.equal(cases.length, 1322);
for (const test of cases) {
  const expression = `${test.function}(${test.args.join(',')})`;
  const execute = () => vm.runInContext(expression, context, { timeout: 1000 });
  if (test.throws) assert.throws(execute, error => error.message === test.throws, expression);
  else assert.equal(execute(), test.value, expression);
}
writeFileSync(path.join(run, 'result.json'), JSON.stringify({ passed: true, officialRuntimeCases: 1300,
  sameInputLoopCases: 22 }) + '\n');
console.log('PASS: 1300 official JVM progression cases and 22 same-input JVM/public-CLI loop cases');
