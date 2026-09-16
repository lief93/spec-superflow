import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';

const code = readFileSync(process.argv[2], 'utf8').replace('export struct RememberPage', 'export class RememberPage');
const parsed = ts.createSourceFile('page.ts', code, ts.ScriptTarget.ES2022, true);
const page = parsed.statements.find(n => ts.isClassDeclaration(n) && n.name?.text === 'RememberPage');
assert.ok(page);
const ordinary = parsed.statements.filter(n => !ts.isImportDeclaration(n) && n !== page)
  .map(n => n.getFullText(parsed)).join('\n');
for (const fail of [false, true]) {
  const context = vm.createContext({exports: {}, moduleFunction: null});
  function run(source) {
    return vm.runInContext(ts.transpileModule(source, {compilerOptions: {
      target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS,
    }}).outputText, context);
  }
  run(ordinary);
  context.exports.__etsSet_showFailure(fail);
  const create = () => {
    const receiver = {};
    // Execute actual emitted field initializers in declaration order, as ArkUI does.
    for (const field of page.members.filter(ts.isPropertyDeclaration)) {
      receiver[field.name.getText(parsed)] = run('moduleFunction = function() { return ' +
        field.initializer.getText(parsed) + '; }').call(receiver);
    }
    return receiver;
  };
  if (fail) {
    assert.throws(create, error => error.name === 'ExceptionInInitializerError');
    assert.equal(context.exports.order, 1, 'failed file must prevent remember side effects');
    assert.throws(create, error => error.name === 'NoClassDefFoundError');
    assert.equal(context.exports.order, 1);
  } else {
    assert.equal(create().state, 2);
    assert.equal(context.exports.order, 12, 'file initialization precedes remembered state');
    assert.equal(create().state, 2);
    assert.equal(context.exports.order, 122, 'new component initializes its state but not the file again');
  }
}
console.log('PASS generated component field initialization: file before remember and failure suppression');
