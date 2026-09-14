import assert from 'node:assert/strict';
import { readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import vm from 'node:vm';
import { ts, assertRuntimeHelpers } from '../runtime-assertions.mjs';

const [output, oracle] = process.argv.slice(2);
const helperSets = {
  GenericModels: [],
  GenericCollections: ['__etsListMap', '__etsListFilter', '__etsArrayIterator', '__etsArrayGet', '__etsArraySet'],
  GenericConsumers: [],
  GenericCases: ['__etsIntDiv', '__etsListGet', '__etsListAdd'],
};
assert.deepEqual(readdirSync(output).sort(), Object.keys(helperSets).map(name => name + '.ets').sort());
const modules = new Map(Object.entries(helperSets).map(([name, helpers]) =>
  [name, assertRuntimeHelpers(join(output, name + '.ets'), helpers)]));
const expectedImports = {
  GenericModels: [], GenericCollections: [],
  GenericConsumers: ['GenericCollections:listCursor', 'GenericCollections:retainList', 'GenericCollections:transformList'],
  GenericCases: ['GenericCollections:arrayCursor', 'GenericCollections:arrayElement', 'GenericCollections:listCursor',
    'GenericCollections:rejectList', 'GenericCollections:replaceElement', 'GenericCollections:retainList', 'GenericCollections:transformList',
    'GenericConsumers:consumeNext', 'GenericConsumers:cursorMore', 'GenericConsumers:mappedCursor', 'GenericConsumers:preserved',
    'GenericModels:GenericBox', 'GenericModels:GenericItem'],
};
for (const [name, text] of modules) {
  const tree = ts.createSourceFile(name + '.ts', text, ts.ScriptTarget.Latest, true);
  const classes = tree.statements.filter(ts.isClassDeclaration).map(node => node.name.text).filter(name => name.startsWith('__ets'));
  assert.deepEqual(classes, name === 'GenericModels' ? [] : ['__etsIterator']);
  const imports = tree.statements.filter(ts.isImportDeclaration).flatMap(node =>
    node.importClause.namedBindings.elements.map(binding => `${node.moduleSpecifier.text.replace(/^\.\//, '')}:${binding.name.text}`));
  assert.deepEqual(imports.sort(), expectedImports[name].sort(), `Exact module imports for ${name}`);
}
const options = { strict: true, noEmit: true, types: [], lib: ['lib.es2020.d.ts'],
  target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS };
const host = ts.createCompilerHost(options);
const virtual = new Map([...modules].map(([name, text]) => [join(output, name + '.ts'), text]));
const exists = host.fileExists.bind(host), read = host.readFile.bind(host), source = host.getSourceFile.bind(host);
host.fileExists = file => virtual.has(file) || exists(file);
host.readFile = file => virtual.get(file) ?? read(file);
host.getSourceFile = (file, version, onError, createNew) => virtual.has(file)
  ? ts.createSourceFile(file, virtual.get(file), version, true) : source(file, version, onError, createNew);
const diagnostics = ts.getPreEmitDiagnostics(ts.createProgram([...virtual.keys()], options, host));
writeFileSync(join(dirname(output), 'typecheck.txt'), diagnostics.map(d => ts.flattenDiagnosticMessageText(d.messageText, '\n')).join('\n'));
assert.equal(diagnostics.length, 0, 'Unchanged generic cross-file output must typecheck');

const negative = join(output, 'WrongGenericArguments.ts');
virtual.set(negative, `import { transformList, listCursor } from './GenericCollections';
import { consumeNext } from './GenericConsumers';
transformList<number, string>([1], (value: string): string => value);
const wrong: string = consumeNext<number>(listCursor<number>([1]));
`);
const rejected = ts.getPreEmitDiagnostics(ts.createProgram([...virtual.keys()], options, host));
assert.deepEqual(rejected.map(d => d.code).sort(), [2322, 2345]);
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
const cases = load('GenericCases');
const expected = readFileSync(oracle, 'utf8').trim().split('\n');
assert.equal(expected.length, 32);
const actual = expected.map(line => {
  const [name, raw] = line.split('|');
  const trace = [], values = [1, 2, 3];
  let result;
  try {
    const args = raw ? raw.split(',').map(value => value === 'null' ? null : Number(value))
      : name === 'mapMutation' || name === 'filterMutation' ? [values, trace]
      : name === 'cursorMutation' ? [values]
      : ['tracePipeline', 'emptyPipeline', 'mapFailure', 'filterFailure'].includes(name) ? [trace] : [];
    result = 'value:' + String(cases[name](...args));
  } catch (failure) {
    const category = /^(ArithmeticException|ConcurrentModificationException|NoSuchElementException)(?::|$)/.exec(failure.message)?.[1];
    assert.ok(category, `Unexpected target failure ${failure}`);
    result = 'error:' + category;
  }
  return `${name}|${raw}|${result}|${trace.join(',')}|${values.join(',')}`;
});
assert.deepEqual(actual, expected, 'Same-input JVM/host values, mutation state, evaluation prefix and exception category');

const collections = load('GenericCollections'), consumers = load('GenericConsumers'), models = load('GenericModels');
const first = new models.GenericItem(3), second = new models.GenericItem(-2), values = [first, second];
const kept = consumers.preserved(values);
assert.notEqual(kept, values);
assert.equal(kept[0], first);
assert.equal(kept[1], second);
assert.equal(consumers.consumeNext(collections.listCursor(kept)), first);
const error = new Error('callback identity');
let visited = 0;
assert.throws(() => collections.transformList(values, value => { visited++; throw error; }), caught => caught === error);
assert.equal(visited, 1);
assert.throws(() => collections.retainList(values, value => { throw error; }), caught => caught === error);
assert.deepEqual(values, [first, second]);
writeFileSync(join(dirname(output), 'host-result.json'), JSON.stringify({ passed: true, cases: actual.length,
  actual, expected, imports: expectedImports, runtime: helperSets, genericTypeNegatives: rejected.map(d => d.code),
  objectIdentity: true, freshCollection: true, callbackExceptionIdentity: true, sdk: false }, null, 2) + '\n');
console.log('PASS 32 JVM/public-CLI/host cases; exact generic module imports/runtime closure; object/failure identity and two type negatives');
