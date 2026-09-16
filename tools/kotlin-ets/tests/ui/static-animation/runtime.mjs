import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';

const code = readFileSync(process.argv[2], 'utf8');
// InitialValue contains only Text builders. Keep their real calls and the value
// holder, omitting only the native entry container for host-side observation.
const executable = (code.slice(0, code.lastIndexOf('  build() {')) + '}\n' +
  code.slice(code.indexOf('\nexport class EtsStaticAnimation')))
  .replace(/^import .*;\n/gm, '').replace(/@(Entry|Component|Builder)\s*/g, '')
  .replace('export struct ', 'export class ');
const labels = [];
const chain = new Proxy(() => {}, {get: () => chain, apply: () => chain});
const context = vm.createContext({exports: {}, Alignment: {TopStart: 0},
  Text: value => {labels.push(value); return chain;}});
vm.runInContext(ts.transpileModule(executable, {compilerOptions: {
  target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS,
}}).outputText, context);
new context.exports.InitialValue().InitialValue();
assert.deepEqual(labels, ['Initial half']);
console.log('PASS actual source initial value reaches generated conditional Text');
