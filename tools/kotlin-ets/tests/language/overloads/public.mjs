import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';

assert.equal(process.env.KOTLIN_ETS_BUILD_SLOT, '1', 'Requires a separately granted exclusive public compiler slot');
assert.ok(process.argv[2] && process.argv[3], 'Pass current and baseline focused result.json manifests');
const here = dirname(fileURLToPath(import.meta.url)), root = resolve(here, '../../..');
const fixtures = join(here, 'public-fixtures'), cwd = root;
const focusedPath = resolve(process.argv[2]), baselinePath = resolve(process.argv[3]);
const focused = JSON.parse(readFileSync(focusedPath)), baseline = JSON.parse(readFileSync(baselinePath));
const hash = path => createHash('sha256').update(readFileSync(path)).digest('hex');
assert.equal(focused.passed, true); assert.equal(focused.phase, 'current');
assert.equal(baseline.passed, true); assert.equal(baseline.phase, 'baseline');
assert.equal(focused.expected.length, 30); assert.deepEqual(focused.expected, baseline.expected);
assert.deepEqual(focused.actual, focused.expected);
assert.equal(hash(focused.output.path), focused.output.sha256);
const producerFiles = () => readdirSync(join(root, 'src'), { recursive: true })
  .filter(path => path.endsWith('.kt')).map(path => join(root, 'src', path)).sort();
assert.deepEqual(producerFiles(), focused.inputs.filter(input => input.path.startsWith(join(root, 'src') + '/'))
  .map(input => input.path).sort(), 'Production file set changed since focused proof');
const legacy = [
  { path: join(root, 'tests/language/UnsupportedOverload.kt'),
    sha256: '5e57cc93836b525a2db8eb6d90af5b387b9319d6894cedddcc1b06c0eb444cb0' },
  { path: join(root, 'tests/inheritance/methods/UnsupportedOverload.kt'),
    sha256: '78e12b4c6f3478ec5aefbbb66eb56666db90e30fb8c99fc0ea85773994de6028' },
];
const additional = [fileURLToPath(import.meta.url), focusedPath, baselinePath, join(root, 'kotlin-ets'),
  join(root, 'tests/stdlib/compiler.sh'), ...readdirSync(fixtures).sort().map(name => join(fixtures, name))];
const inputs = [...focused.inputs, ...legacy, ...additional.map(path => ({ path, sha256: hash(path) }))];
function guard() {
  for (const input of inputs) assert.equal(hash(input.path), input.sha256, `Changed input: ${input.path}`);
  assert.deepEqual(producerFiles(), focused.inputs.filter(input => input.path.startsWith(join(root, 'src') + '/'))
    .map(input => input.path).sort());
}
guard();
mkdirSync(join(here, '.work'), { recursive: true });
const work = mkdtempSync(join(here, '.work/public-'));
console.log(`Evidence: ${work}`);
const result = { focusedPath, baselinePath, inputs, legacy, commands: [], outputs: [], comparisons: [] };
const record = () => writeFileSync(join(work, 'result.json'), JSON.stringify(result, null, 2));
record();
// Retain the original negative bytes even if a later accepted migration moves their paths.
legacy.forEach((input, index) => writeFileSync(join(work, `legacy-${index + 1}-original.kt`), readFileSync(input.path)));
const env = { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' };
function run(label, command, args) {
  guard();
  const value = spawnSync(command, args, { cwd, env, encoding: 'utf8', timeout: 600000, maxBuffer: 16 * 1024 * 1024 });
  writeFileSync(join(work, label + '.stdout'), value.stdout ?? '');
  writeFileSync(join(work, label + '.stderr'), value.stderr ?? '');
  result.commands.push({ label, command, args, cwd, status: value.status, error: value.error?.message }); record();
  assert.equal(value.error, undefined); assert.equal(value.status, 0, value.stdout + value.stderr);
  guard();
  return value.stdout;
}
function generate(label, sources, single = false) {
  const output = join(work, label + (single ? '.ets' : ''));
  assert.equal(existsSync(output), false);
  const stdout = run(label, join(root, 'kotlin-ets'), ['--mode', 'language', single ? '--out' : '--out-dir', output, ...sources]);
  const diagnostic = JSON.parse(stdout);
  assert.equal(diagnostic.ok, true);
  assert.equal(diagnostic.frontend, 'Kotlin-2.1.20-K2-FIR2IR');
  const paths = single ? [output] : readdirSync(output).sort().map(name => join(output, name));
  if (!single) assert.deepEqual(paths.map(path => path.slice(path.lastIndexOf('/') + 1)).sort(),
    sources.map(path => path.slice(path.lastIndexOf('/') + 1).replace(/\.kt$/, '.ets')).sort());
  result.outputs.push(...paths.map(path => ({ label, path, sha256: hash(path) }))); record();
  return paths;
}
function moduleLoader(paths) {
  const modules = new Map(paths.map(path => [path.slice(path.lastIndexOf('/') + 1), readFileSync(path, 'utf8')]));
  const cache = new Map();
  function load(name) {
    if (cache.has(name)) return cache.get(name).exports;
    assert.ok(modules.has(name), `Missing generated module: ${name}`);
    const compiled = ts.transpileModule(modules.get(name), {
      compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS }, reportDiagnostics: true,
    });
    assert.deepEqual(compiled.diagnostics, []);
    const module = { exports: {} }; cache.set(name, module);
    vm.runInNewContext(compiled.outputText, { module, exports: module.exports, require(specifier) {
      assert.ok(/^\.\/[^/]+$/.test(specifier), `Unexpected dependency: ${specifier}`);
      return load(specifier.slice(2) + '.ets');
    } }, { timeout: 1000 });
    return module.exports;
  }
  return load;
}
function compare(label, expected, actual) {
  result.comparisons.push({ label, expected, actual }); record(); assert.deepEqual(actual, expected);
}
const compiler = join(root, 'tests/stdlib/compiler.sh');
const cp = run('classpath', 'bash', [compiler, '--classpath']).trim();
const java = join(process.env.JAVA_HOME ?? '/Applications/Android Studio.app/Contents/jbr/Contents/Home', 'bin/java');
function oracle(label, sources, main) {
  const jar = join(work, label + '.jar');
  run(label + '-build', 'bash', [compiler, ...sources, '-d', jar]);
  return run(label + '-run', java, ['-cp', `${jar}:${cp}`, main]).trimEnd().split('\n');
}
const source = join(here, 'Overloads.kt'), seeds = [0, -3, 7, -2147483648, 2147483647];
const expected = oracle('focused-jvm', [source, join(here, 'JvmOracle.kt')], 'overloadfixture.JvmOracleKt');
assert.deepEqual(expected, focused.expected);
const [publicPath] = generate('Overloads', [source], true);
assert.equal(hash(publicPath), focused.output.sha256, 'Complete public ETS must equal exact focused ETS');
const single = moduleLoader([publicPath])('Overloads.ets');
compare('focused-public', expected, seeds.flatMap(seed =>
  ['arityCase', 'numericCase', 'memberCase', 'genericCase', 'classGenericCase', 'effectsCase'].map(name => String(single[name](seed)))));

const crossSources = [join(fixtures, 'CrossFileCalls.kt'), source];
const crossExpected = oracle('cross-jvm', [...crossSources, join(fixtures, 'CrossFileOracle.kt')], 'overloadfixture.CrossFileOracleKt');
assert.equal(crossExpected.length, 5);
const cross = moduleLoader(generate('cross-file', crossSources))('CrossFileCalls.ets');
compare('cross-file-public', crossExpected, seeds.map(seed => String(cross.crossFileCase(seed))));

const topCalls = join(fixtures, 'LegacyTopCalls.kt'), memberCalls = join(fixtures, 'LegacyMemberCalls.kt');
const legacyExpected = oracle('legacy-jvm', [...legacy.map(input => input.path), topCalls, memberCalls,
  join(fixtures, 'LegacyOracle.kt')], 'LegacyOracleKt');
assert.equal(legacyExpected.length, 10);
const top = moduleLoader(generate('legacy-top', [legacy[0].path, topCalls]))('LegacyTopCalls.ets');
const member = moduleLoader(generate('legacy-member', [legacy[1].path, memberCalls]))('LegacyMemberCalls.ets');
compare('unchanged-legacy-public-with-explicit-consumers', legacyExpected,
  seeds.flatMap(seed => [String(top.legacyTopCase(seed)), String(member.legacyMemberCase(seed))]));
guard(); result.passed = true; record();
console.log('PASS public launcher: exact focused ETS hash, 45 original JVM/host pairs, cross-file calls and both unchanged historical inputs; no SDK/native claim');
