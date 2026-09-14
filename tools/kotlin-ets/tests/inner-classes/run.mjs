import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { copyFileSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';

assert.equal(process.env.KOTLIN_ETS_BUILD_SLOT, '1', 'Main must grant the exclusive compiler slot');
const here = dirname(fileURLToPath(import.meta.url)), root = resolve(here, '../..');
const baselineIndex = process.argv.indexOf('--baseline-language'), baseline = baselineIndex >= 0;
assert.ok(!baseline || process.argv[baselineIndex + 1]);
const hash = path => createHash('sha256').update(readFileSync(path)).digest('hex');
const sources = () => readdirSync(join(root, 'src'), { recursive: true }).filter(path => path.endsWith('.kt')).sort();
const live = sources().map(path => ({ path: join(root, 'src', path), sha256: hash(join(root, 'src', path)) }));
mkdirSync(join(here, '.work'), { recursive: true });
const work = mkdtempSync(join(here, baseline ? '.work/red-' : '.work/green-'));
console.log(`Evidence: ${work}`);
const paths = [...sources().map(path => 'src/' + path), 'tests/stdlib/compiler.sh',
  ...['Outer.kt', 'Collisions.kt', 'Calls.kt', 'Oracle.kt', 'Probe.kt', 'run.mjs'].map(path => relative(root, join(here, path)))];
const inputs = paths.map(path => {
  const original = baseline && path === 'src/language/LanguageLowering.kt' ? resolve(process.argv[baselineIndex + 1]) : join(root, path);
  const snapshot = join(work, 'frozen', path), sha256 = hash(original);
  mkdirSync(dirname(snapshot), { recursive: true }); copyFileSync(original, snapshot);
  assert.equal(hash(snapshot), sha256); return { path, original, snapshot, sha256 };
});
const result = { phase: baseline ? 'baseline-language' : 'current', work, live, inputs, commands: [], comparisons: [], passed: false };
const record = () => writeFileSync(join(work, 'result.json'), JSON.stringify(result, null, 2));
function guard() {
  assert.deepEqual(sources().map(path => join(root, 'src', path)), live.map(input => input.path));
  for (const input of live) assert.equal(hash(input.path), input.sha256, `Production changed: ${input.path}`);
  for (const input of inputs) {
    assert.equal(hash(input.original), input.sha256, `Input changed: ${input.original}`);
    assert.equal(hash(input.snapshot), input.sha256, `Snapshot changed: ${input.snapshot}`);
  }
}
function run(label, command, args) {
  guard();
  const value = spawnSync(command, args, { cwd: root,
    env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' },
    encoding: 'utf8', timeout: 600000, maxBuffer: 32 * 1024 * 1024 });
  writeFileSync(join(work, label + '.stdout'), value.stdout ?? '');
  writeFileSync(join(work, label + '.stderr'), value.stderr ?? '');
  result.commands.push({ label, command, args, status: value.status, error: value.error?.message }); record();
  assert.equal(value.error, undefined); assert.equal(value.status, 0, value.stdout + value.stderr);
  guard(); return value.stdout;
}
record();
const frozen = join(work, 'frozen'), fixtures = join(frozen, relative(root, here));
const compiler = join(frozen, 'tests/stdlib/compiler.sh');
const files = ['Outer.kt', 'Collisions.kt', 'Calls.kt'].map(path => join(fixtures, path));
const cp = run('classpath', 'bash', [compiler, '--classpath']).trim();
const oracle = join(work, 'oracle.jar');
run('oracle-build', 'bash', [compiler, ...files, join(fixtures, 'Oracle.kt'), '-d', oracle]);
result.expected = run('oracle', 'java', ['-cp', `${oracle}:${cp}`, 'innerfixture.OracleKt']).trimEnd().split('\n');
assert.equal(result.expected.length, 20); record();
const jar = join(work, 'backend.jar');
run('backend-build', 'bash', [compiler, ...inputs.filter(input => input.path.startsWith('src/')).map(input => input.snapshot),
  join(fixtures, 'Probe.kt'), '-d', jar]);
const output = join(work, 'output'); mkdirSync(output);
run('target', 'java', ['-cp', `${jar}:${cp}`, 'dev.ets.ProbeKt', cp, output, baseline ? 'baseline' : 'current', ...files]);
if (baseline) result.rejection = readFileSync(join(output, 'rejection.txt'), 'utf8');
else {
  assert.equal(readFileSync(join(output, 'negative-count.txt'), 'utf8'), '14');
  const reverse = join(work, 'reverse'); mkdirSync(reverse);
  run('reverse', 'java', ['-cp', `${jar}:${cp}`, 'dev.ets.ProbeKt', cp, reverse, 'current', ...files.toReversed()]);
  const names = readdirSync(join(output, 'modules')).sort();
  assert.deepEqual(names, ['Calls.ets', 'Collisions.ets', 'Outer.ets']);
  result.modules = names.map(name => {
    const path = join(output, 'modules', name), sha256 = hash(path);
    assert.equal(sha256, hash(join(reverse, 'modules', name)), `Input order changed ${name}`);
    return { path, sha256 };
  });
  const texts = new Map(names.map(name => [name, readFileSync(join(output, 'modules', name), 'utf8')]));
  const syntax = new Map([...texts].map(([name, text]) => [name, ts.createSourceFile(name, text, ts.ScriptTarget.Latest, true)]));
  for (const [name, source] of syntax) {
    assert.equal(source.parseDiagnostics.length, 0);
    for (const declaration of source.statements.filter(ts.isImportDeclaration)) {
      const destination = declaration.moduleSpecifier.text.slice(2) + '.ets';
      assert.ok(syntax.has(destination), `Unresolved import in ${name}`);
      assert.ok(ts.isNamedImports(declaration.importClause.namedBindings));
      const exports = syntax.get(destination).statements.filter(node => ts.isFunctionDeclaration(node) || ts.isClassDeclaration(node))
        .filter(node => node.modifiers?.some(modifier => modifier.kind === ts.SyntaxKind.ExportKeyword)).map(node => node.name.text);
      for (const imported of declaration.importClause.namedBindings.elements) {
        assert.equal(imported.propertyName, undefined);
        assert.ok(exports.includes(imported.name.text), `Missing export ${imported.name.text}`);
      }
    }
  }
  function loader(modules) {
    const cache = new Map();
    function load(name) {
      if (cache.has(name)) return cache.get(name).exports;
      assert.ok(modules.has(name), `Unknown generated module ${name}`);
      const compiled = ts.transpileModule(modules.get(name), { compilerOptions: {
        target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS,
      }, reportDiagnostics: true });
      assert.deepEqual(compiled.diagnostics, []);
      const module = { exports: {} }; cache.set(name, module);
      vm.runInNewContext(compiled.outputText, { module, exports: module.exports, require(specifier) {
        assert.ok(specifier.startsWith('./')); return load(specifier.slice(2) + '.ets');
      } }, { timeout: 1000 });
      return module.exports;
    }
    return load;
  }
  function compare(label, exported) {
    const actual = [0, -3, 7, -2147483648, 2147483647].flatMap(seed => exported.cases(seed).split('\n'));
    result.comparisons.push({ label, actual }); record();
    assert.deepEqual(actual, result.expected);
  }
  const load = loader(texts);
  compare('multi-file', load('Calls.ets'));
  assert.equal(load('Outer.ets').Hidden, undefined);
  compare('flat', loader(new Map([['Combined.ets', readFileSync(join(output, 'Combined.ets'), 'utf8')]]))('Combined.ets'));
  for (const file of result.modules) assert.equal(hash(file.path), file.sha256);
}
guard(); result.passed = true; record();
console.log(baseline ? 'PASS expected RED: original JVM executes; inner-unaware language rejects official outer field' :
  'PASS inner classes: 20 JVM outcomes match flat/modules, 14 malformed bindings, deterministic module bytes; no SDK/native claim');
