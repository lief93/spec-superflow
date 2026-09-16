import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';
const code=readFileSync(process.argv[2],'utf8');
const parsed=ts.createSourceFile('page.ts',code.replace('export struct Page','export class Page'),ts.ScriptTarget.ES2022,true);
const ordinary=parsed.statements.filter(n=>!ts.isImportDeclaration(n)&&!(ts.isClassDeclaration(n)&&n.name?.text==='Page')).map(n=>n.getFullText(parsed)).join('\n');
const context=vm.createContext({exports:{},TextAlign:{Start:0},TextOverflow:{Clip:0},FontStyle:{Normal:0,Italic:1},TextDecorationType:{None:0,Underline:1,LineThrough:2}});
vm.runInContext(ts.transpileModule(ordinary,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText,context);
const api=context.exports;
const style=api.underline();
assert.equal(style.textDecoration,1);
const attrs={};
const instance=new Proxy({},{get:(_,name)=>value=>{attrs[name]=value;return instance;}});
for(const [decoration,color,expected,expectedColor] of [[null,null,1,0xffff0000],[0,null,0,0xffff0000],[2,0xff0000ff,2,0xff0000ff]]) {
  api.__etsTextStyleModifier(color,null,null,null,null,null,decoration,null,null,0,100,style,0xff000000).applyNormalAttribute(instance);
  assert.equal(attrs.decoration.type,expected);
  assert.equal(attrs.decoration.color,expectedColor);
}
console.log('PASS native decoration attribute mapping, style precedence and text color');
