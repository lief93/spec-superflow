import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';

const code = readFileSync(process.argv[2], 'utf8').replace('export struct Page', 'export class Page');
assert.match(code, /aboutToAppear\(\): void \{/);
assert.match(code, /__etsActiveUIContext = this\.getUIContext\(\);/);
assert.match(code, /function __etsClearFocus\(\): void \{/);
assert.match(code, /__etsActiveUIContext\?\.getFocusController\(\)\?\.clearFocus\(\);/);
assert.match(code, /export class EtsFocusManager/);
assert.match(code, /export const __etsFocusManager: EtsFocusManager = new EtsFocusManager\(\);/);
assert.match(code, /return __etsFocusManager;/);
const parsed = ts.createSourceFile('page.ts', code, ts.ScriptTarget.ES2022, true);
const page = parsed.statements.find(n => ts.isClassDeclaration(n) && n.name?.text === 'Page');
assert.ok(page);
const ordinary = parsed.statements.filter(n => !ts.isImportDeclaration(n) && n !== page)
  .map(n => n.getFullText(parsed)).join('\n');
const labels = [];
const native = new Proxy({}, {get: () => () => native});
let cleared = 0;
const controller = { clearFocus() { cleared++; } };
const uiContext = { getFocusController() { return controller; } };
const context = vm.createContext({exports: {}, moduleFunction: null, Alignment: {TopStart: 0},
  getContext: () => ({}), Text: label => { labels.push(label); return native; }});
function run(source) {
  return vm.runInContext(ts.transpileModule(source, {compilerOptions: {
    target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS,
  }}).outputText, context);
}
run(ordinary);
assert.equal(context.exports.identity(context.exports.__etsFocusManager), context.exports.__etsFocusManager);
assert.equal(context.exports.currentFocus(), context.exports.__etsFocusManager);
const receiver = { getUIContext() { return uiContext; } };
for (const method of page.members.filter(n => ts.isMethodDeclaration(n) && n.name.getText(parsed) !== 'build')) {
  receiver[method.name.getText(parsed)] = run('moduleFunction = function(' +
    method.parameters.map(p => p.getText(parsed)).join(',') + ') ' + method.body.getText(parsed));
}
receiver.aboutToAppear();
assert.equal(cleared, 0);
receiver.Page();
assert.equal(cleared, 1, 'clearFocus uses the UIContext captured on the entry component');
assert.equal(typeof context.exports.dismiss, 'function');
assert.deepEqual(labels, ['same host']);
console.log('PASS native focus identity, aboutToAppear UIContext capture and FocusController.clearFocus');
