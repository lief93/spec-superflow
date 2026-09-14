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
const run = mkdtempSync(path.join(tests, '.build/runtime-dependencies.'));
console.log(`Runtime dependency evidence: ${run}`);
const cases = [
  { name: 'none', sources: ['None'], helpers: [], check: m => {
    assert.equal(m.plain(5), 7);
    assert.equal(m.nativeMath(7), 21);
    assert.equal(m.helperText(), '__etsIntDiv __etsSubstringFrom');
  } },
  { name: 'division', sources: ['Division'], helpers: ['__etsIntDiv'], check: m => {
    assert.equal(m.divide(-7, 2), -3);
    assert.throws(() => m.divide(1, 0), /ArithmeticException/);
    assert.equal(m.divideAgain(9), 4);
  } },
  { name: 'nested', sources: ['Division', 'Nested'],
    helpers: ['__etsIntDiv', '__etsIntRem', '__etsListGet', '__etsListMap'], check: m => {
      assert.equal(m.nestedResult(17), 5);
      assert.equal(m.classResult(17), 7);
      assert.equal(new m.Calculator(3).initial, 4);
    } },
  { name: 'substring', sources: ['Substring'], helpers: ['__etsSubstring', '__etsSubstringFrom'], check: m => {
    assert.equal(m.tail('abcd', 2), 'cd');
    assert.throws(() => m.tail('abcd', 5), /IndexOutOfBoundsException/);
  } },
];
const results = [];
for (const test of [...cases, { ...cases[2], name: 'nested-repeat' }]) {
  const output = path.join(run, `${test.name}.ets`);
  const args = ['--mode', 'language', '--out', output,
    ...test.sources.map(name => path.join(tests, 'fixtures/runtime', `${name}.kt`))];
  const cli = spawnSync(path.join(root, 'kotlin-ets'), args, { encoding: 'utf8', timeout: 180000 });
  writeFileSync(path.join(run, `${test.name}.stdout`), cli.stdout ?? '');
  writeFileSync(path.join(run, `${test.name}.stderr`), cli.stderr ?? '');
  try {
    assert.equal(cli.status, 0, `public CLI failed: ${cli.stderr}`);
    const text = assertRuntimeHelpers(output, test.helpers);
    const code = ts.transpileModule(text, { compilerOptions: {
      target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS,
    } }).outputText;
    const context = { exports: {} };
    vm.runInNewContext(code, context, { timeout: 10000 });
    test.check(context.exports);
    if (test.name === 'nested-repeat') {
      assert.equal(text, readFileSync(path.join(run, 'nested.ets'), 'utf8'), 'nondeterministic CLI output');
    }
    results.push({ name: test.name, passed: true, helpers: test.helpers });
  } catch (error) {
    results.push({ name: test.name, passed: false, error: error.message });
  }
  writeFileSync(path.join(run, 'result.json'), JSON.stringify(results, null, 2) + '\n');
}
assert.ok(results.every(result => result.passed), JSON.stringify(results, null, 2));
console.log('PASS: public CLI runtime selection, execution, transitive closure, and determinism');
