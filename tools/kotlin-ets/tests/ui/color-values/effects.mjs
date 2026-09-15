import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';

// Execute builder methods, not layout: replace only the native struct shell and
// exclude build(), whose Stack DSL belongs to the actual SDK test.
export function verifyEffects(path) {
  const source = readFileSync(path, 'utf8');
  const parsed = ts.createSourceFile('effects.ts', source.replace('export struct EffectPage', 'export class EffectPage'),
    ts.ScriptTarget.ES2022, true);
  const page = parsed.statements.find(node => ts.isClassDeclaration(node) && node.name?.text === 'EffectPage');
  assert.ok(page);
  const members = page.members.filter(node => node.name?.getText(parsed) !== 'build');
  assert.ok(members.length >= 2);
  const ordinary = parsed.statements.filter(node => node !== page && !ts.isImportDeclaration(node))
    .map(node => node.getFullText(parsed)).join('\n');
  const executable = ordinary + '\nexport class EffectPage {\n' +
    members.map(node => node.getFullText(parsed)).join('\n') + '\n}';
  const texts = [];
  const attributes = { fontColor() { return this; }, attributeModifier() { return this; } };
  const context = vm.createContext({ exports: {}, Builder() {}, Text(text) { texts.push(text); return attributes; } });
  vm.runInContext(ts.transpileModule(executable, { compilerOptions: {
    target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS
  } }).outputText, context, { timeout: 2000 });
  vm.runInContext('new exports.EffectPage().EffectPage()', context, { timeout: 2000 });
  assert.deepEqual(texts, ['1'], 'color argument must execute before later text argument');
  assert.equal(source.split('counter.nextColor()').length - 1, 1);
}

if (process.argv[2]) verifyEffects(process.argv[2]);
