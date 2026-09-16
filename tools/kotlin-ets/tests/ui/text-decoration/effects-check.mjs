import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';
const code=readFileSync(process.argv[2],'utf8').replace('export struct EffectsPage','export class EffectsPage');
const parsed=ts.createSourceFile('page.ts',code,ts.ScriptTarget.ES2022,true);
const page=parsed.statements.find(n=>ts.isClassDeclaration(n)&&n.name?.text==='EffectsPage');
const ordinary=parsed.statements.filter(n=>!ts.isImportDeclaration(n)&&n!==page).map(n=>n.getFullText(parsed)).join('\n');
const context=vm.createContext({exports:{},moduleFunction:null,Alignment:{TopStart:0},TextAlign:{Start:0,Center:1},TextOverflow:{Clip:0},FontStyle:{Normal:0,Italic:1},TextDecorationType:{None:0,Underline:1,LineThrough:2}});
function run(source){return vm.runInContext(ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText,context);}
run(ordinary);
context.exports.effectStyle();
assert.equal(context.exports.order,1234,'TextStyle constructor parameter order');
context.exports.order=0;
const receiver={};
const native=new Proxy({},{get:()=>()=>native});
context.Text=()=>native;
for(const method of page.members.filter(n=>ts.isMethodDeclaration(n)&&n.name.getText(parsed)!=='build')) {
  receiver[method.name.getText(parsed)]=run('moduleFunction = function('+method.parameters.map(p=>p.getText(parsed)).join(',')+') '+method.body.getText(parsed));
}
receiver.EffectsPage();
// style was written first at the call site: its 1234 must precede the Text overrides' 123.
assert.equal(context.exports.order,1234123,'Text call argument evaluation order');
console.log('PASS generated TextStyle and Text side-effect order: 1234 / 1234123');
