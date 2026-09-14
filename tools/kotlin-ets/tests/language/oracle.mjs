import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';

const source = readFileSync(process.argv[2], 'utf8');
if (process.argv[3] === 'LanguageSlice.kt') {
  assert.match(source, /this\.total = this\.total \+ amount \| 0;/,
    'discarded assignment should be a direct statement, not a void IIFE');
  assert.doesNotMatch(source, /\(\(\): void => \{/,
    'ordinary assignments in this fixture need no void IIFEs');
  assert.match(source, /const mapped: number = \(\(\): number => \{/,
    'named arguments with side effects must retain their evaluation scope');
}
const compiled = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
  reportDiagnostics: true,
});
assert.deepEqual(compiled.diagnostics, [], 'generated TypeScript must parse');
const context = { exports: {} };
vm.runInNewContext(compiled.outputText, context, { timeout: 1000 });
if (process.argv[3] === 'SingletonSlice.kt') {
  assert.equal(context.exports.singletonInitCount(), 0);
  assert.equal(context.exports.singletonSlice(), 9);
  assert.equal(context.exports.singletonInitCount(), 1);
  assert.equal(context.exports.singletonSlice(), 15);
  assert.equal(context.exports.singletonInitCount(), 1);
  console.log('PASS singleton references share state across aliases and calls');
  process.exit(0);
}
if (process.argv[3] === 'ControlSlice.kt') {
  assert.equal(context.exports.controlSlice(), 7);
  console.log('PASS do/while, break, captured mutation and Unit lambda return');
  process.exit(0);
}
if (process.argv[3] === 'ScopeSlice.kt') {
  assert.equal(context.exports.scopeSlice(), 10);
  console.log('PASS symbol-bound compiler temporaries preserve temporary-looking source names');
  process.exit(0);
}
if (process.argv[3] === 'DataSlice.kt') {
  assert.equal(context.exports.dataSlice(), 'Invoice(item=blue, count=5):8:blue:8');
  assert.equal(context.exports.describe('text'), 'text');
  assert.equal(context.exports.describe(8), 'other');
  assert.equal(context.exports.checked('text'), 'text');
  assert.throws(() => context.exports.checked(8), /ClassCastException/);
  assert.equal(context.exports.safe('text'), 'text');
  assert.equal(context.exports.safe(8), null);
  assert.equal(context.exports.namedLabel(new context.exports.Named('x')), 'Named(x)');
  assert.equal(context.exports.namedLabel(null), 'null');
  console.log('PASS language data class, copy defaults, destructuring, type checks and casts');
  process.exit(0);
}
const actual = context.exports.languageSlice();
// Kotlin evaluates the supplied named arguments in source order: add() gives 5,
// then add(1) gives 6. Formal parameter order remains first, second, third.
assert.equal(actual, '645:6:8:10');
console.log('PASS language runtime: named argument order, defaults, class mutation, loop, lambda, when');
