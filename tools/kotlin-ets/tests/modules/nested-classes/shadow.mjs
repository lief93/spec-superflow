import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { copyFileSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';

assert.equal(process.env.KOTLIN_ETS_BUILD_SLOT, '1', 'Main must grant the exclusive compiler slot');
const here = dirname(fileURLToPath(import.meta.url)), root = resolve(here, '../../..');
const baselineIndex = process.argv.indexOf('--baseline-jar');
assert.ok(baselineIndex < 0 || process.argv[baselineIndex + 1], 'Pass the retained pre-fix backend JAR');
const baseline = baselineIndex >= 0 ? resolve(process.argv[baselineIndex + 1]) : undefined;
const hash = path => createHash('sha256').update(readFileSync(path)).digest('hex');
const productionPaths = () => readdirSync(join(root, 'src'), { recursive: true }).filter(path => path.endsWith('.kt'))
  .sort().map(path => join(root, 'src', path));
const live = productionPaths().map(path => ({ path, sha256: hash(path) }));
mkdirSync(join(here, '.work'), { recursive: true });
const work = mkdtempSync(join(here, baseline ? '.work/shadow-red-' : '.work/shadow-green-'));
console.log(`Evidence: ${work}`);
const inputs = [...live.map(input => input.path), ...['shadow.mjs', 'ShadowProbe.kt', 'shadow/Types.kt', 'shadow/Uses.kt', 'shadow/Oracle.kt',
  'shadow/Baseline.kt', 'shadow/BaselineOracle.kt']
  .map(path => join(here, path)), join(root, 'tests/stdlib/compiler.sh'), ...(baseline ? [baseline] : [])].map(path => {
  const snapshot = join(work, 'frozen', path === baseline ? 'baseline.jar' : relative(root, path)), sha256 = hash(path);
  mkdirSync(dirname(snapshot), { recursive: true }); copyFileSync(path, snapshot);
  assert.equal(hash(snapshot), sha256);
  return { path, snapshot, sha256 };
});
const result = { phase: baseline ? 'baseline' : 'current', work, live, inputs, commands: [], comparisons: [], passed: false };
const record = () => writeFileSync(join(work, 'result.json'), JSON.stringify(result, null, 2));
function guard() {
  assert.deepEqual(productionPaths(), live.map(input => input.path));
  for (const input of [...live, ...inputs]) assert.equal(hash(input.path), input.sha256, `Input changed: ${input.path}`);
  for (const input of inputs) assert.equal(hash(input.snapshot), input.sha256, `Snapshot changed: ${input.snapshot}`);
}
function run(label, command, args) {
  guard();
  const value = spawnSync(command, args, { cwd: root, encoding: 'utf8', timeout: 600000, maxBuffer: 32 * 1024 * 1024,
    env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' } });
  writeFileSync(join(work, label + '.stdout'), value.stdout ?? '');
  writeFileSync(join(work, label + '.stderr'), value.stderr ?? '');
  result.commands.push({ label, command, args, status: value.status, error: value.error?.message }); record();
  assert.equal(value.error, undefined); assert.equal(value.status, 0, value.stdout + value.stderr);
  guard(); return value;
}
record();
const frozen = join(work, 'frozen'), fixture = join(frozen, relative(root, here));
const compiler = join(frozen, 'tests/stdlib/compiler.sh');
const sources = (baseline ? ['Baseline.kt'] : ['Types.kt', 'Uses.kt']).map(name => join(fixture, 'shadow', name));
const cp = run('classpath', 'bash', [compiler, '--classpath']).stdout.trim();
const oracle = join(work, 'oracle.jar');
run('oracle-build', 'bash', [compiler, ...sources, join(fixture, baseline ? 'shadow/BaselineOracle.kt' : 'shadow/Oracle.kt'), '-d', oracle]);
result.expected = run('oracle', 'java', ['-cp', `${oracle}:${cp}`, baseline ? 'reviewshadow.BaselineOracleKt' : 'shadowfixture.OracleKt'])
  .stdout.trimEnd().split('\n');
assert.equal(result.expected.length, baseline ? 1 : 55); assert.equal(result.expected[baseline ? 0 : 22], '7'); record();
const jar = baseline ? join(frozen, 'baseline.jar') : join(work, 'backend.jar');
if (!baseline) run('backend-build', 'bash', [compiler, ...inputs.filter(input => input.path.startsWith(join(root, 'src') + '/'))
  .map(input => input.snapshot), join(fixture, 'ShadowProbe.kt'), '-d', jar]);
const forward = join(work, 'forward'); mkdirSync(forward);
if (baseline) {
  const cli = ['-cp', `${jar}:${cp}`, 'dev.ets.MainKt', '--mode', 'language', '--classpath', cp];
  run('modules', 'java', [...cli, '--out-dir', join(forward, 'modules'), ...sources]);
  run('flat', 'java', [...cli, '--out', join(forward, 'Combined.ets'), ...sources]);
} else {
  run('forward', 'java', ['-cp', `${jar}:${cp}`, 'dev.ets.ShadowProbeKt', cp, forward, ...sources]);
  const reverse = join(work, 'reverse'); mkdirSync(reverse);
  run('reverse', 'java', ['-cp', `${jar}:${cp}`, 'dev.ets.ShadowProbeKt', cp, reverse, ...sources.toReversed()]);
  for (const name of ['Types.ets', 'Uses.ets']) assert.equal(hash(join(forward, 'modules', name)), hash(join(reverse, 'modules', name)));
}
const names = readdirSync(join(forward, 'modules')).sort();
assert.deepEqual(names, baseline ? ['Baseline.ets'] : ['Types.ets', 'Uses.ets']);
const texts = new Map(names.map(name => [name, readFileSync(join(forward, 'modules', name), 'utf8')]));
const parsed = new Map([...texts].map(([name, text]) => [name, ts.createSourceFile(name, text, ts.ScriptTarget.Latest, true)]));
for (const [name, source] of parsed) {
  assert.equal(source.parseDiagnostics.length, 0);
  for (const statement of source.statements.filter(ts.isImportDeclaration)) {
    const owner = parsed.get(statement.moduleSpecifier.text.slice(2) + '.ets');
    assert.ok(owner, `Missing module in ${name}`);
    assert.ok(ts.isNamedImports(statement.importClause.namedBindings));
    for (const imported of statement.importClause.namedBindings.elements) {
      assert.equal(imported.propertyName, undefined);
      assert.ok(owner.statements.some(node => node.name?.text === imported.name.text &&
        node.modifiers?.some(modifier => modifier.kind === ts.SyntaxKind.ExportKeyword)));
    }
  }
}
function loadModules(modules) {
  const cache = new Map();
  function load(name) {
    if (cache.has(name)) return cache.get(name).exports;
    assert.ok(modules.has(name));
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
const functions = ['result', 'localResult', 'initializerResult', 'laterBinding', 'nestedResult', 'closureResult',
  'checkedResult', 'holderResult', 'unshadowedResult', 'siblingResult', 'typeOnlyResult'];
for (const [label, calls] of [
  ['multi-file', loadModules(texts)(baseline ? 'Baseline.ets' : 'Uses.ets')],
  ['flat', loadModules(new Map([['Combined.ets', readFileSync(join(forward, 'Combined.ets'), 'utf8')]]))('Combined.ets')],
]) {
  if (baseline) {
    let observed;
    try { observed = { value: calls.result(7) }; } catch (error) { observed = { name: error.name, message: error.message }; }
    result.comparisons.push({ label, jvm: '7', observed }); record();
    assert.equal(observed.name, 'TypeError'); assert.match(observed.message, /Node is not a constructor/);
  } else {
    const actual = [0, -3, 7, -2147483648, 2147483647].flatMap(seed => functions.map(name => String(calls[name](seed))));
    result.comparisons.push({ label, expected: result.expected, actual }); record();
    assert.deepEqual(actual, result.expected);
  }
}
result.modules = names.map(name => ({ path: join(forward, 'modules', name), sha256: hash(join(forward, 'modules', name)) }));
guard(); result.passed = true; record();
console.log(baseline ? 'PASS expected RED: original JVM result(7)=7; unchanged baseline flat/modules throw Node TypeError' :
  'PASS lexical class values: 55 JVM outcomes match flat/modules; unchanged source bindings, minimal fresh name and deterministic imports');
