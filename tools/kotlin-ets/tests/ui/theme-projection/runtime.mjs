import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';

const code = readFileSync(process.argv[2], 'utf8').replace('export struct Page', 'export class Page');
const parsed = ts.createSourceFile('page.ts', code, ts.ScriptTarget.ES2022, true);
const ordinary = parsed.statements.filter(n => !ts.isImportDeclaration(n) &&
  !(ts.isClassDeclaration(n) && n.name?.text === 'Page')).map(n => n.getFullText(parsed)).join('\n');
let primary = 0xff1256ab;
const reads = [];
const context = vm.createContext({exports: {}, getContext: () => ({resourceManager: {
  getColorByNameSync(name) {
    reads.push(name);
    if (name === 'kotlin_ets_material_primary') return primary;
    throw new Error('missing resource');
  },
  getOverrideResourceManager() {throw new Error('Current native configuration must not be overridden');},
}})});
vm.runInContext(ts.transpileModule(ordinary, {compilerOptions: {
  target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS,
}}).outputText, context);
const palette = context.exports.__etsCurrentProjectColorScheme();
assert.deepEqual(reads, []);
assert.equal(palette.primary, primary);
primary = 0xffda3478;
assert.equal(palette.primary, primary);
assert.throws(() => palette.tertiary, /kotlin_ets_material_tertiary.*missing resource/);
console.log('PASS current host resources, lazy reads, refreshed values and named failures');
