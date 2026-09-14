import assert from 'node:assert/strict';
import { readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import vm from 'node:vm';
import { ts, assertRuntimeHelpers } from '../runtime-assertions.mjs';

const [output, oracle, producer] = process.argv.slice(2);
const manifest = JSON.parse(readFileSync(new URL('./cases.json', import.meta.url), 'utf8'));
assert.equal(manifest.length, 21);
assert.equal(new Set(manifest.map(value => JSON.stringify(value))).size, 21);
const bindings = readFileSync(join(producer, 'bindings.tsv'), 'utf8').trim().split('\n').map(line => {
  const [module, sourceName, kotlinType, name, id] = line.split('\t');
  return { module, sourceName, kotlinType, name, id };
});
assert.equal(bindings.length, 6);
assert.equal(new Set(bindings.map(binding => binding.id)).size, 6);
const intChoice = bindings.find(binding => binding.sourceName === 'choose' && binding.kotlinType === 'kotlin.Int');
assert.ok(intChoice);
const choiceImports = bindings.filter(binding => binding.sourceName === 'choose').map(binding => `${binding.module}:${binding.name}`);
const helperSets = {
  OverloadChoices: ['__etsIntDiv', '__etsListAdd'], OverloadSelector: ['__etsListAdd'],
  OverloadPipeline: ['__etsListMap', '__etsListFilter', '__etsArrayIterator'], OverloadConsumer: [],
  OverloadCases: ['__etsListGet', '__etsListAdd'],
};
const imports = {
  OverloadChoices: [], OverloadSelector: choiceImports, OverloadPipeline: [], OverloadConsumer: [],
  OverloadCases: [...choiceImports, 'OverloadSelector:OverloadItem', 'OverloadSelector:OverloadSelector',
    'OverloadPipeline:overloadMapped', 'OverloadPipeline:overloadFiltered', 'OverloadPipeline:overloadCursor',
    'OverloadConsumer:overloadNext', 'OverloadConsumer:overloadMore'],
};
assert.deepEqual(readdirSync(output).sort(), Object.keys(helperSets).map(name => name + '.ets').sort());
const modules = new Map(Object.entries(helperSets).map(([name, helpers]) =>
  [name, assertRuntimeHelpers(join(output, name + '.ets'), helpers)]));
for (const [name, text] of modules) {
  assert.equal(text, readFileSync(join(producer, 'modules', name + '.ets'), 'utf8'), 'Public CLI must equal actual-IR producer output');
  const tree = ts.createSourceFile(name + '.ts', text, ts.ScriptTarget.Latest, true);
  const classes = tree.statements.filter(ts.isClassDeclaration).map(node => node.name.text).filter(value => value.startsWith('__ets'));
  assert.deepEqual(classes, ['OverloadPipeline', 'OverloadConsumer', 'OverloadCases'].includes(name) ? ['__etsIterator'] : []);
  const actual = tree.statements.filter(ts.isImportDeclaration).flatMap(node =>
    node.importClause.namedBindings.elements.map(binding => `${node.moduleSpecifier.text.replace(/^\.\//, '')}:${binding.name.text}`));
  assert.deepEqual(actual.sort(), [...imports[name]].sort(), `Exact overload imports for ${name}`);
  // These fixtures require no type test. Numeric selection must already be bound in IR.
  const typeTests = [];
  function visit(node) { if (node.kind === ts.SyntaxKind.TypeOfExpression) typeTests.push(node); ts.forEachChild(node, visit); }
  visit(tree);
  assert.equal(typeTests.length, 0, 'No runtime typeof overload dispatcher');
}
const options = { strict: true, noEmit: true, types: [], lib: ['lib.es2020.d.ts'],
  target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS };
const host = ts.createCompilerHost(options);
const virtual = new Map([...modules].map(([name, text]) => [join(output, name + '.ts'), text]));
virtual.set(join(output, 'SdkConsumer.ts'), readFileSync(new URL('./SdkConsumer.ets', import.meta.url), 'utf8'));
const exists = host.fileExists.bind(host), read = host.readFile.bind(host), source = host.getSourceFile.bind(host);
host.fileExists = file => virtual.has(file) || exists(file);
host.readFile = file => virtual.get(file) ?? read(file);
host.getSourceFile = (file, version, onError, createNew) => virtual.has(file)
  ? ts.createSourceFile(file, virtual.get(file), version, true) : source(file, version, onError, createNew);
const diagnostics = ts.getPreEmitDiagnostics(ts.createProgram([...virtual.keys()], options, host));
writeFileSync(join(dirname(output), 'typecheck.txt'), diagnostics.map(d => ts.flattenDiagnosticMessageText(d.messageText, '\n')).join('\n'));
assert.equal(diagnostics.length, 0, 'Unchanged modules and SDK consumer must typecheck');
const intMember = bindings.find(binding => binding.sourceName === 'select' && binding.kotlinType === 'kotlin.Int');
assert.ok(intMember);
const negative = join(output, 'WrongOverloads.ts');
virtual.set(negative, `import { ${intChoice.name} } from './OverloadChoices';
import { OverloadSelector } from './OverloadSelector';
import { overloadMapped, overloadCursor } from './OverloadPipeline';
import { overloadNext } from './OverloadConsumer';
${intChoice.name}('wrong', []);
new OverloadSelector([]).${intMember.name}('wrong');
overloadMapped<number, number>([1], (value: string): number => 1);
const wrong: string = overloadNext<number>(overloadCursor<number>([1]));
`);
const rejected = ts.getPreEmitDiagnostics(ts.createProgram([...virtual.keys()], options, host));
assert.deepEqual(rejected.map(d => d.code).sort(), [2322, 2345, 2345, 2345]);
virtual.delete(negative);
const cache = new Map();
function load(name) {
  name = name.replace(/^\.\//, '');
  if (cache.has(name)) return cache.get(name);
  assert.ok(modules.has(name), `Unexpected source import ${name}`);
  const exports = {};
  cache.set(name, exports);
  const code = ts.transpileModule(modules.get(name), { compilerOptions: { ...options, noEmit: false } }).outputText;
  vm.runInNewContext(code, { exports, require: load }, { timeout: 1000 });
  return exports;
}
const cases = load('OverloadCases'), selectors = load('OverloadSelector'), choices = load('OverloadChoices');
const expected = readFileSync(oracle, 'utf8').trim().split('\n');
assert.deepEqual(expected.map(line => line.split('|').slice(0, 2)), manifest.map(({ name, args }) => [name, args.join(',')]));
const actual = manifest.map(({ name, args }) => {
  const trace = [];
  let result;
  try {
    let value;
    if (name === 'identity') {
      const first = new selectors.OverloadItem(1), second = new selectors.OverloadItem(2), values = [first, second];
      const retained = cases.objectPipeline(values, trace);
      value = retained !== values && retained.length === 1 && retained[0] === second &&
        values.length === 2 && values[0] === first && values[1] === second;
    } else if (name === 'errorIdentity') {
      const marker = new Error('identity');
      const callback = item => { choices[intChoice.name](item, trace); throw marker; };
      value = false;
      try { cases.errorPipeline([1, 2], callback, callback, args[0]); }
      catch (failure) { value = failure === marker; }
    } else value = cases[name](...args, trace);
    result = 'value:' + String(value);
  } catch (failure) {
    const category = /^(ArithmeticException|ConcurrentModificationException|NoSuchElementException)(?::|$)/.exec(failure.message)?.[1];
    assert.ok(category, `Unexpected overload failure ${failure}`);
    result = 'error:' + category;
  }
  return `${name}|${args.join(',')}|${result}|${trace.join(',')}`;
});
assert.deepEqual(actual, expected, 'Same-input static selection, order/count, mutation/error prefixes and identity');
const sdk = {};
vm.runInNewContext(ts.transpileModule(virtual.get(join(output, 'SdkConsumer.ts')),
  { compilerOptions: { ...options, noEmit: false } }).outputText, { exports: sdk, require: load }, { timeout: 1000 });
assert.equal(sdk.overloadSdkCheck(), 6452);
writeFileSync(join(dirname(output), 'host-result.json'), JSON.stringify({ passed: true, cases: actual.length,
  actual, expected, imports, runtime: helperSets, typeNegatives: rejected.map(d => d.code), sdk: false }, null, 2) + '\n');
console.log('PASS 21 overload JVM/public-CLI/host cases, six preserved source bindings, exact imports/closure, four type negatives');
