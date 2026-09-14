import assert from 'node:assert/strict';
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';
import { ts } from './runtime-assertions.mjs';

const tests = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(tests, '../..');
const env = { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' };
mkdirSync(path.join(tests, '.build'), { recursive: true });
const run = mkdtempSync(path.join(tests, '.build/iteration.'));
console.log(`Iteration evidence: ${run}`);
function command(name, executable, args) {
  const result = spawnSync(executable, args, { env, encoding: 'utf8', timeout: 300000 });
  writeFileSync(path.join(run, `${name}.stdout`), result.stdout ?? '');
  writeFileSync(path.join(run, `${name}.stderr`), result.stderr ?? '');
  writeFileSync(path.join(run, `${name}.json`), JSON.stringify({ executable, args,
    status: result.status, signal: result.signal, error: result.error?.message }, null, 2) + '\n');
  assert.equal(result.status, 0, `${name}: ${result.stdout}\n${result.stderr}`);
  return result.stdout;
}
const fixture = path.join(tests, 'fixtures/Iteration.kt');
const hash = () => createHash('sha256').update(readFileSync(fixture)).digest('hex');
const originalHash = hash();
const jar = path.join(run, 'oracle.jar');
command('jvm-compile', 'bash', [path.join(tests, 'compiler.sh'), '-d', jar, fixture,
  path.join(tests, 'IterationOracle.kt')]);
const cp = command('classpath', 'bash', [path.join(tests, 'compiler.sh'), '--classpath']).trim();
const oracle = command('jvm', 'java', ['-cp', `${cp}:${jar}`, 'iterationcases.IterationOracleKt']);
const output = path.join(run, 'iteration.ets');
command('cli', path.join(root, 'kotlin-ets'), ['--mode', 'language', '--out', output, fixture]);
const emitted = ts.transpileModule(readFileSync(output, 'utf8'), { compilerOptions: {
  target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS,
}, reportDiagnostics: true });
assert.deepEqual(emitted.diagnostics, []);
const context = vm.createContext({ exports: {} });
vm.runInContext(emitted.outputText, context, { timeout: 1000 });
const cases = oracle.trim().split('\n').map(line => JSON.parse(line));
assert.equal(cases.length, 69);
for (const test of cases) {
  const evaluate = () => vm.runInContext(test.expression, context, { timeout: 1000 });
  if (test.throws) assert.throws(evaluate, error => error.message.startsWith(test.throws), test.expression);
  else assert.deepEqual(JSON.parse(JSON.stringify(evaluate())), test.value, test.expression);
}
assert.equal(hash(), originalHash, 'JVM and CLI must compile unchanged same input');
writeFileSync(path.join(run, 'result.json'), JSON.stringify({ passed: true, cases: cases.length,
  sourceSha256: originalHash }) + '\n');
console.log(`PASS: ${cases.length} JVM/public-CLI array-backed iteration/progression cases`);
