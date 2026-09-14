import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';

const work = process.argv[2];
function load(name) {
  const parsed = ts.transpileModule(readFileSync(join(work, name + '.ets'), 'utf8'), {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS }, reportDiagnostics: true,
  });
  assert.deepEqual(parsed.diagnostics, []);
  const context = { exports: {} };
  vm.runInNewContext(parsed.outputText, context, { timeout: 1000 });
  return context.exports;
}
const original = load('Original');
const renamed = load('Renamed');
const actual = [
  [0, 3, 6].map(n => original.execute(n)),
  [0, 3, 6].map(n => renamed.evaluate(n)),
  [original.combine(2), original.combine(2, 8, 1), renamed.assemble(4), renamed.assemble(4, 2, 3)],
];
const expected = readFileSync(join(work, 'jvm.stdout'), 'utf8').trim().split('\n').map(line => line.split(',').map(Number));
assert.deepEqual(actual, expected);
assert.notDeepEqual(actual[0], actual[1], 'changed defaults/object inputs must affect execution');
console.log('PASS JVM/printed-target host differential: renamed methods, arguments, defaults, closure, condition/while, object');
