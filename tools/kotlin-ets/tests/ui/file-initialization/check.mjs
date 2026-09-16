import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';

const code = readFileSync(process.argv[2], 'utf8').replace('export struct Page', 'export class Page');
const parsed = ts.createSourceFile('page.ts', code, ts.ScriptTarget.ES2022, true);
const page = parsed.statements.find(n => ts.isClassDeclaration(n) && n.name?.text === 'Page');
assert.ok(page);
const ordinary = parsed.statements.filter(n => !ts.isImportDeclaration(n) && n !== page)
  .map(n => n.getFullText(parsed)).join('\n');
const labels = [];
const native = new Proxy({}, {get: () => () => native});
const context = vm.createContext({exports: {}, moduleFunction: null, Alignment: {TopStart: 0},
  Text: label => { labels.push(label); return native; }});
function run(source) {
  return vm.runInContext(ts.transpileModule(source, {compilerOptions: {
    target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS,
  }}).outputText, context);
}
run(ordinary);
// Separately transpiled builder methods still reference the module's exported globals.
for (const name of ['showOther', 'showFailure']) {
  Object.defineProperty(context, name, {get: () => context.exports[name]});
}
const receiver = {};
for (const method of page.members.filter(n => ts.isMethodDeclaration(n) && n.name.getText(parsed) !== 'build')) {
  receiver[method.name.getText(parsed)] = run('moduleFunction = function(' +
    method.parameters.map(p => p.getText(parsed)).join(',') + ') ' + method.body.getText(parsed));
}
assert.equal(context.exports.order, 0, 'module load must not initialize lazy files');
receiver.Page();
assert.equal(context.exports.order, 12, 'root enters its file even without reading a property');
receiver.Page();
assert.equal(context.exports.order, 12, 'repeat rendering does not repeat file initialization');
context.exports.__etsSet_showOther(true);
receiver.Page();
assert.equal(context.exports.order, 1234, 'callee file initialization precedes its default argument');
receiver.Page();
assert.equal(context.exports.order, 12344, 'defaults repeat but file initialization does not');
assert.equal(labels.filter(label => label === 'Other: 4').length, 2);
context.exports.__etsSet_showOther(false);
context.exports.__etsSet_showFailure(true);
assert.throws(() => receiver.Page(), error => error.name === 'ExceptionInInitializerError');
assert.equal(context.exports.order, 123445);
assert.throws(() => receiver.Page(), error => error.name === 'NoClassDefFoundError');
assert.equal(context.exports.order, 123445, 'failed initialization is never retried');
assert.ok(!labels.includes('Must not render'));
console.log('PASS generated builder initialization: laziness, order, defaults, re-entry and failure');
