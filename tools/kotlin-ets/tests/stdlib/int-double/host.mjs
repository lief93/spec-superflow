import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import vm from 'node:vm';
import { ts, assertRuntimeHelpers } from '../runtime-assertions.mjs';

const [output, oracle] = process.argv.slice(2);
const text = assertRuntimeHelpers(output, ['__etsIntDiv', '__etsListAdd']);
const tree = ts.createSourceFile(output, text, ts.ScriptTarget.Latest, true);
assert.equal(tree.statements.filter(ts.isClassDeclaration).length, 0);
const options = { strict: true, noEmit: true, types: [], target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS };
const virtual = output + '.ts', host = ts.createCompilerHost(options), source = host.getSourceFile.bind(host);
host.getSourceFile = (file, ...args) => file === virtual ? ts.createSourceFile(file, text, args[0], true) : source(file, ...args);
const diagnostics = ts.getPreEmitDiagnostics(ts.createProgram([virtual], options, host));
assert.deepEqual(diagnostics.map(d => ts.flattenDiagnosticMessageText(d.messageText, '\n')), []);
const context = { exports: {} };
vm.runInNewContext(ts.transpileModule(text, { compilerOptions: { ...options, noEmit: false } }).outputText, context, { timeout: 1000 });
const inputs = [ -2147483648, -2147483647, -16777217, -16777216, -1, 0, 1, 16777216, 16777217, 2147483646, 2147483647 ];
const cases = [...inputs.map(value => ['widen', value]), ...[-1, 0, 1].map(value => ['receiverOnce', value])];
const expected = readFileSync(oracle, 'utf8').trim().split('\n');
assert.deepEqual(expected.map(line => line.split('|').slice(0, 2)), cases.map(([name, value]) => [name, String(value)]));
const actual = cases.map(([name, input]) => {
  const trace = [];
  let result;
  try {
    const value = context.exports[name](input, trace);
    const view = new DataView(new ArrayBuffer(8));
    view.setFloat64(0, value, false);
    result = 'bits:' + view.getBigUint64(0, false).toString(16);
  } catch (failure) {
    assert.match(failure.message, /^ArithmeticException(?::|$)/);
    result = 'error:ArithmeticException';
  }
  return `${name}|${input}|${result}|${trace.join(',')}`;
});
assert.deepEqual(actual, expected, 'Exact IEEE double bits and evaluate-once/error traces from JVM');
writeFileSync(join(dirname(output), 'host-result.json'), JSON.stringify({ passed: true, pairs: 14, actual, expected, sdk: false }, null, 2));
console.log('PASS 14 Int.toDouble JVM/public-CLI/host pairs; exact IEEE bits, receiver once, error prefix, no conversion runtime');
