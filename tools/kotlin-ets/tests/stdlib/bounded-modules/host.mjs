import assert from 'node:assert/strict';
import { readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import vm from 'node:vm';
import { ts, assertRuntimeHelpers } from '../runtime-assertions.mjs';

const [output, oracle] = process.argv.slice(2);
const helperSets = {
  BoundedModels: ['__etsIntDiv', '__etsListAdd'],
  BoundedCollections: ['__etsListMap', '__etsListFilter'],
  BoundedIterators: ['__etsArrayIterator'],
  BoundedCases: ['__etsListGet', '__etsListAdd'],
};
assert.deepEqual(readdirSync(output).sort(), Object.keys(helperSets).map(name => name + '.ets').sort());
const modules = new Map(Object.entries(helperSets).map(([name, helpers]) =>
  [name, assertRuntimeHelpers(join(output, name + '.ets'), helpers)]));
const imports = {
  BoundedModels: [],
  BoundedCollections: ['BoundedModels:BoundedBase', 'BoundedModels:BoundedReadable'],
  BoundedIterators: ['BoundedCollections:retainPositive', 'BoundedModels:BoundedBase', 'BoundedModels:BoundedReadable'],
  BoundedCases: ['BoundedCollections:readClasses', 'BoundedCollections:readValues', 'BoundedCollections:rejectPositive',
    'BoundedCollections:retainClasses', 'BoundedCollections:retainPositive',
    'BoundedIterators:boundedCursor', 'BoundedIterators:classCursor', 'BoundedIterators:keptCursor',
    'BoundedIterators:nextClass', 'BoundedIterators:nextRead',
    'BoundedModels:BoundedBase', 'BoundedModels:BoundedFailure', 'BoundedModels:BoundedMutator',
    'BoundedModels:BoundedNumber', 'BoundedModels:BoundedReadable', 'BoundedModels:BoundedText'],
};
for (const [name, text] of modules) {
  const tree = ts.createSourceFile(name + '.ts', text, ts.ScriptTarget.Latest, true);
  const classes = tree.statements.filter(ts.isClassDeclaration).map(node => node.name.text).filter(name => name.startsWith('__ets'));
  assert.deepEqual(classes, ['BoundedIterators', 'BoundedCases'].includes(name) ? ['__etsIterator'] : []);
  const actual = tree.statements.filter(ts.isImportDeclaration).flatMap(node =>
    node.importClause.namedBindings.elements.map(binding => `${node.moduleSpecifier.text.replace(/^\.\//, '')}:${binding.name.text}`));
  assert.deepEqual(actual.sort(), imports[name].sort(), `Exact bounded source imports for ${name}`);
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
assert.equal(diagnostics.length, 0, 'Unchanged bounded generic modules must typecheck');
const negative = join(output, 'WrongBounds.ts');
virtual.set(negative, `import { readClasses, readValues } from './BoundedCollections';
import { BoundedText } from './BoundedModels';
readValues<number, BoundedText>([new BoundedText('wrong')]);
readClasses<BoundedText>([new BoundedText('wrong')]);
`);
const rejected = ts.getPreEmitDiagnostics(ts.createProgram([...virtual.keys()], options, host));
assert.deepEqual(rejected.map(d => d.code), [2344, 2344]);
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
const cases = load('BoundedCases'), models = load('BoundedModels'), collections = load('BoundedCollections');
const expected = readFileSync(oracle, 'utf8').trim().split('\n');
assert.equal(expected.length, 26);
const actual = expected.map(line => {
  const [name, raw] = line.split('|');
  const trace = [];
  let result;
  try {
    let value;
    if (name === 'identity') {
      const first = new models.BoundedNumber(3, trace), second = new models.BoundedNumber(-1, trace);
      const source = [first, second], retained = collections.retainPositive(source);
      value = retained !== source && retained.length === 1 && retained[0] === first && source[1] === second && source.length === 2;
    } else if (name === 'errorIdentity') {
      const marker = new Error('identity');
      const source = [new models.BoundedAction(() => { trace.push(1); throw marker; }), new models.BoundedAction(() => { trace.push(2); return 2; })];
      value = false;
      try { (raw === 'true' ? collections.retainPositive : collections.readValues)(source); }
      catch (failure) { value = failure === marker; }
    } else {
      const args = name === 'stringRead' ? [raw] : name === 'memberMutation' ? [raw === 'true', trace]
        : [...(raw ? raw.split(',').map(Number) : []), trace];
      value = cases[name](...args);
    }
    result = 'value:' + String(value);
  } catch (failure) {
    const category = /^(ArithmeticException|ConcurrentModificationException|NoSuchElementException)(?::|$)/.exec(failure.message)?.[1];
    assert.ok(category, `Unexpected bounded target failure ${failure}`);
    result = 'error:' + category;
  }
  return `${name}|${raw}|${result}|${trace.join(',')}`;
});
assert.deepEqual(actual, expected, 'Same original helpers: values, member order/error prefixes, mutation, object/error identity');
writeFileSync(join(dirname(output), 'host-result.json'), JSON.stringify({ passed: true, cases: actual.length,
  actual, expected, imports, runtime: helperSets, boundTypeNegatives: rejected.map(d => d.code), sdk: false }, null, 2) + '\n');
console.log('PASS 26 bounded JVM/public-CLI/host cases, exact imports/runtime closure, source-object/error identity and two bound type negatives');
