import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { copyFileSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { basename, dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';

assert.equal(process.env.KOTLIN_ETS_BUILD_SLOT, '1', 'Main must grant the exclusive compiler slot');
const here = dirname(fileURLToPath(import.meta.url)), root = resolve(here, '../../..');
const baselineIndex = process.argv.indexOf('--baseline-language'), baseline = baselineIndex >= 0;
assert.ok(!baseline || process.argv[baselineIndex + 1]);
const hash = path => createHash('sha256').update(readFileSync(path)).digest('hex');
const sources = () => readdirSync(join(root, 'src'), { recursive: true }).filter(path => path.endsWith('.kt')).sort();
const live = sources().map(path => ({ path: join(root, 'src', path), sha256: hash(join(root, 'src', path)) }));
const groups = [
  { name: 'global', files: ['Global.kt'], entry: 'Global.ets' },
  { name: 'overload', files: ['Overload.kt'], entry: 'Overload.ets' },
  { name: 'imported', files: ['imported/Helpers.kt', 'imported/Use.kt'], entry: 'Use.ets' },
];
mkdirSync(join(here, '.work'), { recursive: true });
const work = mkdtempSync(join(here, baseline ? '.work/shadow-red-' : '.work/shadow-green-'));
console.log(`Evidence: ${work}`);
const paths = [...sources().map(path => 'src/' + path), 'tests/stdlib/compiler.sh',
  ...['ShadowProbe.kt', 'shadow.mjs', 'shadow/Oracle.kt', ...groups.flatMap(group => group.files.map(path => 'shadow/' + path))]
    .map(path => relative(root, join(here, path)))];
const inputs = paths.map(path => {
  const original = baseline && path === 'src/language/LanguageLowering.kt' ? resolve(process.argv[baselineIndex + 1]) : join(root, path);
  const snapshot = join(work, 'frozen', path), sha256 = hash(original);
  mkdirSync(dirname(snapshot), { recursive: true }); copyFileSync(original, snapshot);
  assert.equal(hash(snapshot), sha256); return { path, original, snapshot, sha256 };
});
const result = { phase: baseline ? 'baseline-language' : 'current', work, live, inputs, commands: [], cases: [], passed: false };
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
function loader(texts) {
  const cache = new Map();
  function load(name) {
    if (cache.has(name)) return cache.get(name).exports;
    assert.ok(texts.has(name), `Missing module ${name}`);
    const parsed = ts.createSourceFile(name, texts.get(name), ts.ScriptTarget.Latest, true);
    assert.equal(parsed.parseDiagnostics.length, 0);
    const compiled = ts.transpileModule(texts.get(name), { compilerOptions: {
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
record();
const frozen = join(work, 'frozen'), fixtures = join(frozen, relative(root, here));
const compiler = join(frozen, 'tests/stdlib/compiler.sh');
const cp = run('classpath', 'bash', [compiler, '--classpath']).trim();
const oracle = join(work, 'oracle.jar');
run('oracle-build', 'bash', [compiler, ...groups.flatMap(group => group.files.map(path => join(fixtures, 'shadow', path))),
  join(fixtures, 'shadow/Oracle.kt'), '-d', oracle]);
result.expected = run('oracle', 'java', ['-cp', `${oracle}:${cp}`, 'captureshadow.OracleKt']).trimEnd().split('\n');
assert.equal(result.expected.length, 15);
assert.deepEqual(result.expected.slice(6, 9), ['17', '17', '17']); record();
const jar = join(work, 'backend.jar');
run('backend-build', 'bash', [compiler, ...inputs.filter(input => input.path.startsWith('src/')).map(input => input.snapshot),
  join(fixtures, 'ShadowProbe.kt'), '-d', jar]);
for (const [index, group] of groups.entries()) {
  const output = join(work, group.name); mkdirSync(output);
  run(group.name, 'java', ['-cp', `${jar}:${cp}`, 'dev.ets.ShadowProbeKt', cp, output,
    baseline ? 'baseline' : 'current', ...group.files.map(path => join(fixtures, 'shadow', path))]);
  const evidence = { name: group.name, expected: result.expected.filter((_, i) => i % groups.length === index) };
  result.cases.push(evidence); record();
  if (baseline) evidence.rejection = readFileSync(join(output, 'rejection.txt'), 'utf8');
  else {
    const names = readdirSync(join(output, 'modules')).sort();
    assert.deepEqual(names, group.files.map(path => basename(path).replace(/\.kt$/, '.ets')).sort());
    evidence.modules = names.map(name => ({ path: join(output, 'modules', name), sha256: hash(join(output, 'modules', name)) }));
    const texts = new Map(names.map(name => [name, readFileSync(join(output, 'modules', name), 'utf8')]));
    if (group.name === 'imported') {
      const parsed = ts.createSourceFile('Use.ets', texts.get('Use.ets'), ts.ScriptTarget.Latest, true);
      const imports = parsed.statements.filter(ts.isImportDeclaration);
      assert.equal(imports.length, 1);
      assert.equal(imports[0].moduleSpecifier.text, './Helpers');
      assert.ok(ts.isNamedImports(imports[0].importClause.namedBindings));
      const binding = imports[0].importClause.namedBindings.elements;
      assert.equal(binding.length, 1); assert.equal(binding[0].name.text, '$seed_0');
      assert.equal(binding[0].propertyName, undefined);
      assert.equal(typeof loader(texts)('Helpers.ets').$seed_0, 'function');
    }
    const values = exported => [0, -3, 7, -2147483648, 2147483647].map(seed => String(exported.result(seed)));
    evidence.modulesActual = values(loader(texts)(group.entry)); record();
    assert.deepEqual(evidence.modulesActual, evidence.expected);
    const flat = readFileSync(join(output, 'Combined.ets'), 'utf8');
    evidence.flatActual = values(loader(new Map([['Combined.ets', flat]]))('Combined.ets')); record();
    assert.deepEqual(evidence.flatActual, evidence.expected);
    for (const file of evidence.modules) assert.equal(hash(file.path), file.sha256);
  }
  record();
}
guard(); result.passed = true; record();
console.log(baseline ? 'PASS expected RED: 3 canonical helper calls rejected before flat/module emission; JVM 17' :
  'PASS capture shadow: 15 JVM results match flat/modules, stable/fresh/imported names and source identities preserved');
