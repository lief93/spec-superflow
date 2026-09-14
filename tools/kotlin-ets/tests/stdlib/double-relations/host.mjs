import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import vm from 'node:vm';
import { ts, assertRuntimeHelpers } from '../runtime-assertions.mjs';

const [output, oracle] = process.argv.slice(2);
const text = assertRuntimeHelpers(output, ['__etsListAdd']);
const options = { strict: true, noEmit: true, types: [], target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS };
const virtual = output + '.ts', host = ts.createCompilerHost(options), source = host.getSourceFile.bind(host);
host.getSourceFile = (file, ...args) => file === virtual ? ts.createSourceFile(file, text, args[0], true) : source(file, ...args);
const diagnostics = ts.getPreEmitDiagnostics(ts.createProgram([virtual], options, host));
assert.deepEqual(diagnostics.map(d => ts.flattenDiagnosticMessageText(d.messageText, '\n')), []);
const context = { exports: {} };
vm.runInNewContext(ts.transpileModule(text, { compilerOptions: { ...options, noEmit: false } }).outputText, context, { timeout: 1000 });
const values = [-Infinity, -1, -0, 0, 1, Infinity, NaN];
assert.ok(Object.is(values[2], -0) && Object.is(values[3], 0));
const cases = ['less', 'lessEqual', 'greater', 'greaterEqual'].flatMap(name =>
  values.flatMap((left, i) => values.map((right, j) => [name, i, j])));
assert.equal(cases.length, 196);
const expected = readFileSync(oracle, 'utf8').trim().split('\n');
assert.deepEqual(expected.map(line => line.split('|').slice(0, 2)), cases.map(([name, i, j]) => [name, `${i},${j}`]));
const actual = cases.map(([name, i, j]) => {
  const trace = [];
  const value = context.exports[name](values[i], values[j], trace);
  assert.deepEqual(trace, [1, 2], 'Left operand then right, each once, including NaN');
  assert.equal(typeof value, 'boolean');
  return `${name}|${i},${j}|${value}|${trace.join(',')}`;
});
assert.deepEqual(actual, expected, 'Independent JVM IEEE relations for all input pairs');
writeFileSync(join(dirname(output), 'host-result.json'), JSON.stringify({ passed: true, pairs: 196, actual, expected, sdk: false }, null, 2));
console.log('PASS 196 Double relation JVM/public-CLI/host pairs; NaN/infinity/signed zero, operands once/in order, no comparison runtime');
