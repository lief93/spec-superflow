import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';

const code = readFileSync(process.argv[2], 'utf8');
const parsed = ts.createSourceFile('page.ts', code.replace('export struct DefaultPage', 'export class DefaultPage'), ts.ScriptTarget.ES2022, true);
const ordinary = parsed.statements.filter(node => !ts.isImportDeclaration(node) &&
  !(ts.isClassDeclaration(node) && node.name?.text === 'DefaultPage')).map(node => node.getFullText(parsed)).join('\n');
const context = vm.createContext({ exports: {},
  __etsFontApi: { registerFont: () => assert.fail('Default family must not register a local font') } });
vm.runInContext(ts.transpileModule(ordinary, { compilerOptions: { target: ts.ScriptTarget.ES2022,
  module: ts.ModuleKind.CommonJS } }).outputText, context);
assert.equal(context.exports.__etsFontFamilyName(context.exports.defaultFamily(), 400, 0), 'HarmonyOS Sans');
assert.equal(context.exports.__etsFontFamilyName(context.exports.defaultFamily(), 700, 1), 'HarmonyOS Sans');
console.log('PASS source FontFamily.Default through ordinary return value to native font selection');
