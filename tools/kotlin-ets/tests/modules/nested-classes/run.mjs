import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { copyFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { basename, dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';

assert.equal(process.env.KOTLIN_ETS_BUILD_SLOT, '1', 'Main must grant the exclusive compiler slot');
const here = dirname(fileURLToPath(import.meta.url)), root = resolve(here, '../../..');
const baselineIndex = process.argv.indexOf('--baseline-root');
const baseline = baselineIndex >= 0;
assert.ok(!baseline || process.argv[baselineIndex + 1], 'Pass a preserved backend source snapshot');
const baselineRoot = baseline ? resolve(process.argv[baselineIndex + 1]) : undefined;
const hash = path => createHash('sha256').update(readFileSync(path)).digest('hex');
const ktFiles = directory => readdirSync(directory, { recursive: true }).filter(path => path.endsWith('.kt')).sort();
const livePaths = () => ktFiles(join(root, 'src')).map(path => join(root, 'src', path));
const live = livePaths().map(path => ({ path, sha256: hash(path) }));
mkdirSync(join(here, '.work'), { recursive: true });
const work = mkdtempSync(join(here, baseline ? '.work/red-' : '.work/green-'));
console.log(`Evidence: ${work}`);
const sourceRoot = baselineRoot ?? root;
const paths = [
  ...ktFiles(join(sourceRoot, 'src')).map(path => ({ path: join(sourceRoot, 'src', path), relative: 'src/' + path })),
  ...[...ktFiles(here), 'run.mjs'].filter(path => !path.startsWith('.work/')).map(path => ({
    path: join(here, path), relative: relative(root, join(here, path)),
  })),
  { path: join(root, 'tests/stdlib/compiler.sh'), relative: 'tests/stdlib/compiler.sh' },
];
const inputs = paths.map(input => {
  const sha256 = hash(input.path), snapshot = join(work, 'frozen', input.relative);
  mkdirSync(dirname(snapshot), { recursive: true }); copyFileSync(input.path, snapshot);
  assert.equal(hash(snapshot), sha256);
  return { ...input, snapshot, sha256 };
});
const result = { phase: baseline ? 'baseline' : 'current', work, live, inputs, commands: [], comparisons: [], passed: false };
const record = () => writeFileSync(join(work, 'result.json'), JSON.stringify(result, null, 2));
function guard() {
  assert.deepEqual(livePaths(), live.map(input => input.path), 'Production source set changed');
  for (const input of live) assert.equal(hash(input.path), input.sha256, `Production changed: ${input.path}`);
  for (const input of inputs) {
    assert.equal(hash(input.path), input.sha256, `Input changed: ${input.path}`);
    assert.equal(hash(input.snapshot), input.sha256, `Snapshot changed: ${input.snapshot}`);
  }
}
const env = { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' };
function run(label, command, args, status = 0) {
  guard();
  const value = spawnSync(command, args, { cwd: root, env, encoding: 'utf8', timeout: 600000, maxBuffer: 32 * 1024 * 1024 });
  writeFileSync(join(work, label + '.stdout'), value.stdout ?? '');
  writeFileSync(join(work, label + '.stderr'), value.stderr ?? '');
  result.commands.push({ label, command, args, status: value.status, error: value.error?.message }); record();
  assert.equal(value.error, undefined); assert.equal(value.status, status, value.stdout + value.stderr);
  guard(); return value;
}
record();
const frozen = join(work, 'frozen'), fixtures = join(frozen, relative(root, here), 'fixtures');
const compiler = join(frozen, 'tests/stdlib/compiler.sh');
const sources = ['AClasses.kt', 'BLocals.kt', 'Calls.kt'].map(name => join(fixtures, name));
const cp = run('classpath', 'bash', [compiler, '--classpath']).stdout.trim();
const oracle = join(work, 'oracle.jar');
run('oracle-build', 'bash', [compiler, ...sources, join(fixtures, 'JvmOracle.kt'), '-d', oracle]);
result.expected = run('oracle', 'java', ['-cp', `${oracle}:${cp}`, 'nestedfixture.JvmOracleKt']).stdout.trimEnd().split('\n');
assert.equal(result.expected.length, 15); record();
const jar = join(work, 'backend.jar');
run('backend-build', 'bash', [compiler, ...inputs.filter(input => input.relative.startsWith('src/')).map(input => input.snapshot),
  join(frozen, relative(root, here), 'Bindings.kt'), join(frozen, relative(root, here), 'Probe.kt'), '-d', jar]);
const forward = join(work, 'forward'); mkdirSync(forward);
const first = run('forward', 'java', ['-cp', `${jar}:${cp}`, 'dev.ets.ProbeKt', cp, forward,
  baseline ? 'baseline' : 'current', ...sources], baseline ? 1 : 0);
if (baseline) {
  assert.match(first.stderr, /Unsupported nested source class declaration|Local classes are not supported by the ETS local declaration phase/);
  assert.equal(existsSync(join(forward, 'modules')), false);
  result.expectedRejection = 'Source nested/local classes rejected before target output';
} else {
  const reverse = join(work, 'reverse'); mkdirSync(reverse);
  run('reverse', 'java', ['-cp', `${jar}:${cp}`, 'dev.ets.ProbeKt', cp, reverse, 'current', ...sources.toReversed()]);
  assert.equal(readFileSync(join(forward, 'negative-count.txt'), 'utf8'), '11');
  const outputs = readdirSync(join(forward, 'modules')).sort();
  assert.deepEqual(outputs, sources.map(path => basename(path).replace(/\.kt$/, '.ets')).sort());
  result.modules = outputs.map(name => {
    const path = join(forward, 'modules', name), sha256 = hash(path);
    assert.equal(sha256, hash(join(reverse, 'modules', name)), `Input-order drift: ${name}`);
    return { path, sha256 };
  });
  const texts = new Map(outputs.map(name => [name, readFileSync(join(forward, 'modules', name), 'utf8')]));
  const syntax = new Map([...texts].map(([name, text]) => [name, ts.createSourceFile(name, text, ts.ScriptTarget.Latest, true)]));
  for (const [name, source] of syntax) {
    assert.equal(source.parseDiagnostics.length, 0);
    for (const declaration of source.statements.filter(ts.isImportDeclaration)) {
      const destination = declaration.moduleSpecifier.text.slice(2) + '.ets';
      assert.ok(syntax.has(destination), `Unresolved import in ${name}`);
      assert.ok(ts.isNamedImports(declaration.importClause.namedBindings));
      const exports = syntax.get(destination).statements.filter(node => ts.isFunctionDeclaration(node) ||
        ts.isClassDeclaration(node) || ts.isInterfaceDeclaration(node))
        .filter(node => node.modifiers?.some(modifier => modifier.kind === ts.SyntaxKind.ExportKeyword)).map(node => node.name.text);
      for (const imported of declaration.importClause.namedBindings.elements) {
        assert.equal(imported.propertyName, undefined, 'No generated-source alias pass');
        assert.ok(exports.includes(imported.name.text), `Missing exported binding: ${imported.name.text}`);
      }
    }
  }
  function loader(modules) {
    const cache = new Map();
    function load(name) {
      if (cache.has(name)) return cache.get(name).exports;
      assert.ok(modules.has(name), `Unknown generated module: ${name}`);
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
  function compare(label, calls) {
    const actual = [0, -3, 7, -2147483648, 2147483647].flatMap(seed =>
      [calls.nestedCase(seed), calls.localCase(seed), String(calls.identityCase(seed))]);
    result.comparisons.push({ label, expected: result.expected, actual }); record();
    assert.deepEqual(actual, result.expected);
  }
  const load = loader(texts);
  compare('multi-file', load('Calls.ets'));
  assert.equal(load('BLocals.ets').Local, undefined);
  assert.equal(load('BLocals.ets').Local_1, undefined);
  const flat = readFileSync(join(forward, 'Combined.ets'), 'utf8');
  compare('flat', loader(new Map([['Combined.ets', flat]]))('Combined.ets'));
}
guard(); result.passed = true; record();
console.log(baseline ? 'PASS expected RED: original JVM succeeds; nested/local target declarations reject before output' :
  'PASS nested classes: 15 JVM cases match flat/modules, 11 typed negatives, deterministic source identities/bindings; no SDK/native claim');
