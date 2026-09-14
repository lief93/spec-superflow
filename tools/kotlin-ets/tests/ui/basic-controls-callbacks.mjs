import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';

for (const name of ['callback0.ts', 'callback1.ts']) {
  const source = readFileSync(join(process.argv[2], name), 'utf8');
  const compiled = ts.transpileModule(source, {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
    reportDiagnostics: true,
  });
  assert.deepEqual(compiled.diagnostics, []);
  const context = vm.createContext({ exports: {}, selected: false });
  vm.runInContext(compiled.outputText, context);
  for (const value of [true, false, true]) {
    assert.equal(context.exports.callback(value), undefined);
    assert.equal(context.selected, value, 'callback must assign its supplied Boolean, not a fixed preview value');
  }
}
console.log('PASS emitted Checkbox/Switch callbacks execute true/false/true updates through the shared language printer');
