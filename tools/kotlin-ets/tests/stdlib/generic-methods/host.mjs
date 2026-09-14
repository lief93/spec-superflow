import assert from 'node:assert/strict';
import { readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import vm from 'node:vm';
import { ts, assertRuntimeHelpers } from '../runtime-assertions.mjs';

const [output, oracle] = process.argv.slice(2);
const caseManifest = JSON.parse(readFileSync(new URL('./cases.json', import.meta.url), 'utf8'));
assert.equal(caseManifest.length, 22);
const helperSets = {
  MethodContracts: [], MethodProjectors: ['__etsListAdd'],
  MethodPipeline: ['__etsListMap', '__etsListFilter', '__etsArrayIterator'], MethodConsumers: [],
  MethodCases: ['__etsIntDiv', '__etsListGet', '__etsListAdd', '__etsListMap'],
};
assert.deepEqual(readdirSync(output).sort(), Object.keys(helperSets).map(name => name + '.ets').sort());
const modules = new Map(Object.entries(helperSets).map(([name, helpers]) =>
  [name, assertRuntimeHelpers(join(output, name + '.ets'), helpers)]));
const imports = {
  MethodContracts: [], MethodProjectors: ['MethodContracts:MethodProjector'],
  MethodPipeline: ['MethodContracts:MethodProjector'], MethodConsumers: [],
  MethodCases: ['MethodConsumers:MethodConsumer', 'MethodContracts:MethodItem', 'MethodContracts:MethodProjector',
    'MethodPipeline:MethodPipeline', 'MethodProjectors:MethodBase', 'MethodProjectors:MethodDerived'],
};
for (const [name, text] of modules) {
  const tree = ts.createSourceFile(name + '.ts', text, ts.ScriptTarget.Latest, true);
  const classes = tree.statements.filter(ts.isClassDeclaration).map(node => node.name.text).filter(name => name.startsWith('__ets'));
  assert.deepEqual(classes, ['MethodPipeline', 'MethodConsumers', 'MethodCases'].includes(name) ? ['__etsIterator'] : []);
  const actual = tree.statements.filter(ts.isImportDeclaration).flatMap(node =>
    node.importClause.namedBindings.elements.map(binding => `${node.moduleSpecifier.text.replace(/^\.\//, '')}:${binding.name.text}`));
  assert.deepEqual(actual.sort(), imports[name].sort(), `Exact generic member imports for ${name}`);
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
assert.equal(diagnostics.length, 0, 'Unchanged generic member modules and manual SDK consumer must typecheck');
const negative = join(output, 'WrongMethods.ts');
virtual.set(negative, `import { MethodDerived } from './MethodProjectors';
import { MethodPipeline } from './MethodPipeline';
import { MethodConsumer } from './MethodConsumers';
const derived = new MethodDerived<number>([]);
derived.project<string>(1, (value: number): number => value);
derived.project<string>('wrong', (value: number): string => value.toString());
new MethodConsumer().next<string>(new MethodPipeline<number>(derived).cursor([1]));
derived.project<number, string>(1, (value: number): number => value);
`);
const rejected = ts.getPreEmitDiagnostics(ts.createProgram([...virtual.keys()], options, host));
assert.deepEqual(rejected.map(d => d.code).sort(), [2345, 2345, 2345, 2558]);
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
const cases = load('MethodCases'), contracts = load('MethodContracts'), projectors = load('MethodProjectors'), pipelines = load('MethodPipeline');
const expected = readFileSync(oracle, 'utf8').trim().split('\n');
assert.deepEqual(expected.map(line => line.split('|').slice(0, 2)), caseManifest.map(({ name, args }) => [name, args.join(',')]));
const actual = caseManifest.map(({ name, args }) => {
  const trace = [];
  let result;
  try {
    let value;
    if (name === 'identity') {
      const first = new contracts.MethodItem(3), second = new contracts.MethodItem(-1), source = [first, second];
      const retained = new pipelines.MethodPipeline(new projectors.MethodDerived(trace)).selected(source,
        item => { trace.push(item.value); return item.value > 0; }, false);
      value = retained !== source && retained.length === 1 && retained[0] === first && source.length === 2 && source[1] === second;
    } else if (name === 'errorIdentity') {
      const marker = new Error('identity');
      const pipeline = new pipelines.MethodPipeline(new projectors.MethodDerived(trace));
      value = false;
      try {
        if (args[0]) pipeline.selected([1, 2], item => { trace.push(item); throw marker; }, false);
        else pipeline.mapped([1, 2], item => { trace.push(item); throw marker; }, () => true);
      } catch (failure) { value = failure === marker; }
    } else value = cases[name](...args, trace);
    result = 'value:' + String(value);
  } catch (failure) {
    const category = /^(ArithmeticException|ConcurrentModificationException|NoSuchElementException)(?::|$)/.exec(failure.message)?.[1];
    assert.ok(category, `Unexpected generic member failure ${failure}`);
    result = 'error:' + category;
  }
  return `${name}|${args.join(',')}|${result}|${trace.join(',')}`;
});
assert.deepEqual(actual, expected, 'Same-input generic dispatch, member/argument order, mutation/error prefixes and identities');
writeFileSync(join(dirname(output), 'host-result.json'), JSON.stringify({ passed: true, cases: actual.length,
  actual, expected, imports, runtime: helperSets, methodTypeNegatives: rejected.map(d => d.code), sdk: false }, null, 2) + '\n');
console.log('PASS 22 generic-member JVM/public-CLI/host cases, exact imports/runtime closure and four method type negatives');
