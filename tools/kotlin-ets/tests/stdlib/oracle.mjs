import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import vm from 'node:vm';

// Type erasure is only for host testing the public CLI's ETS output.
assert.equal(process.argv.length, 4, 'Usage: node oracle.mjs <public-CLI-output.ets> <jvm-oracle.jsonl>');
const require = createRequire(import.meta.url);
const ts = require(process.env.KOTLIN_ETS_TYPESCRIPT ??
  '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js');
const emitted = ts.transpileModule(readFileSync(process.argv[2], 'utf8'), {
  compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS },
  reportDiagnostics: true,
});
assert.deepEqual(emitted.diagnostics, [], 'Generated output must parse');
const context = vm.createContext({ exports: {} });
vm.runInContext(emitted.outputText, context);
const cases = readFileSync(process.argv[3], 'utf8').trim().split('\n').map(line => JSON.parse(line));
assert.ok(cases.length > 50, 'JVM oracle must contain the whole fixture suite');
for (const test of cases) {
  if (test.throws) {
    assert.throws(() => vm.runInContext(test.expression, context),
      error => error.message.includes(test.throws), test.expression);
  } else {
    assert.equal(vm.runInContext(test.expression, context), test.value, test.expression);
  }
}
console.log(`PASS: ${cases.length} JVM/ETS differential cases`);
