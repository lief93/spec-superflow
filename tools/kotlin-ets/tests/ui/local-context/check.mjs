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
const host = {resourceManager: {}};
const labels = [];
let reads = 0;
const native = new Proxy({}, {get: () => () => native});
const context = vm.createContext({exports: {}, moduleFunction: null, Alignment: {TopStart: 0},
  getContext: () => { reads++; return host; }, Text: label => { labels.push(label); return native; }});
function run(source) {
  return vm.runInContext(ts.transpileModule(source, {compilerOptions: {
    target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS,
  }}).outputText, context);
}
run(ordinary);
assert.equal(context.exports.currentContext(), host);
assert.equal(context.exports.identity(host), host);
const receiver = {};
for (const method of page.members.filter(n => ts.isMethodDeclaration(n) && n.name.getText(parsed) !== 'build')) {
  receiver[method.name.getText(parsed)] = run('moduleFunction = function(' +
    method.parameters.map(p => p.getText(parsed)).join(',') + ') ' + method.body.getText(parsed));
}
receiver.Page();
assert.deepEqual(labels, ['same host']);
assert.equal(reads, 2, 'one native context read per source currentContext invocation');
console.log('PASS native host identity through source parameters, returns and UI consumption');
