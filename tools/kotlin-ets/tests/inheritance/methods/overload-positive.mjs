import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdirSync, mkdtempSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';

const here = dirname(fileURLToPath(import.meta.url)), root = resolve(here, '../../..');
const kind = process.argv[2];
assert.ok(kind === 'top' || kind === 'member', 'Choose top or member historical fixture');
const index = kind === 'top' ? 0 : 1;
const fixtures = join(root, 'tests/language/overloads/public-fixtures');
const hash = path => createHash('sha256').update(readFileSync(path)).digest('hex');
const legacy = [
  { path: join(root, 'tests/language/UnsupportedOverload.kt'),
    sha256: '5e57cc93836b525a2db8eb6d90af5b387b9319d6894cedddcc1b06c0eb444cb0' },
  { path: join(here, 'UnsupportedOverload.kt'),
    sha256: '78e12b4c6f3478ec5aefbbb66eb56666db90e30fb8c99fc0ea85773994de6028' },
];
const companions = ['LegacyTopCalls.kt', 'LegacyMemberCalls.kt', 'LegacyOracle.kt'].map(name => join(fixtures, name));
const producerFiles = () => readdirSync(join(root, 'src'), { recursive: true }).filter(path => path.endsWith('.kt'))
  .sort().map(path => join(root, 'src', path));
const production = producerFiles();
const inputs = [...legacy, ...[...production, ...companions, fileURLToPath(import.meta.url), join(root, 'kotlin-ets'),
  join(root, 'tests/stdlib/compiler.sh')].map(path => ({ path, sha256: hash(path) }))];
function guard() {
  assert.deepEqual(producerFiles(), production);
  for (const input of inputs) assert.equal(hash(input.path), input.sha256, `Changed input: ${input.path}`);
}
guard();
mkdirSync(join(here, '.work'), { recursive: true });
const work = mkdtempSync(join(here, `.work/overload-${kind}-`));
console.log(`Evidence: ${work}`);
const result = { kind, acceptedMigrationEvidence: 'tests/language/overloads/.work/public-WddLTc/result.json',
  inputs, commands: [] };
const record = () => writeFileSync(join(work, 'result.json'), JSON.stringify(result, null, 2));
record();
writeFileSync(join(work, 'original.kt'), readFileSync(legacy[index].path));
const env = { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' };
function run(label, command, args) {
  guard();
  const value = spawnSync(command, args, { cwd: root, env, encoding: 'utf8', timeout: 600000, maxBuffer: 16 * 1024 * 1024 });
  writeFileSync(join(work, label + '.stdout'), value.stdout ?? '');
  writeFileSync(join(work, label + '.stderr'), value.stderr ?? '');
  result.commands.push({ label, command, args, cwd: root, status: value.status, error: value.error?.message }); record();
  assert.equal(value.error, undefined); assert.equal(value.status, 0, value.stdout + value.stderr);
  guard(); return value.stdout;
}
const compiler = join(root, 'tests/stdlib/compiler.sh'), oracle = join(work, 'oracle.jar');
const cp = run('classpath', 'bash', [compiler, '--classpath']).trim();
run('jvm-build', 'bash', [compiler, ...legacy.map(input => input.path), ...companions, '-d', oracle]);
const java = join(process.env.JAVA_HOME ?? '/Applications/Android Studio.app/Contents/jbr/Contents/Home', 'bin/java');
const expected = run('jvm-run', java, ['-cp', `${oracle}:${cp}`, 'LegacyOracleKt']).trimEnd().split('\n');
assert.equal(expected.length, 10);
result.expected = expected.filter((_, position) => position % 2 === index); record();
const output = join(work, 'modules');
const diagnostic = JSON.parse(run('public-cli', join(root, 'kotlin-ets'), ['--mode', 'language', '--out-dir', output,
  legacy[index].path, companions[index]]));
assert.equal(diagnostic.ok, true); assert.equal(diagnostic.frontend, 'Kotlin-2.1.20-K2-FIR2IR');
const entry = kind === 'top' ? 'LegacyTopCalls.ets' : 'LegacyMemberCalls.ets';
assert.deepEqual(readdirSync(output).sort(), [entry, 'UnsupportedOverload.ets'].sort());
result.outputs = readdirSync(output).sort().map(name => ({ path: join(output, name), sha256: hash(join(output, name)) }));
record();
const cache = new Map();
function load(name) {
  assert.ok(name === entry || name === 'UnsupportedOverload.ets', `Unexpected generated import: ${name}`);
  if (cache.has(name)) return cache.get(name).exports;
  const module = { exports: {} }; cache.set(name, module);
  const compiled = ts.transpileModule(readFileSync(join(output, name), 'utf8'), {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS }, reportDiagnostics: true,
  });
  assert.deepEqual(compiled.diagnostics, []);
  vm.runInNewContext(compiled.outputText, { module, exports: module.exports, require(specifier) {
    assert.ok(/^\.\/[^/]+$/.test(specifier)); return load(specifier.slice(2) + '.ets');
  } }, { timeout: 1000 });
  return module.exports;
}
const exported = load(entry), method = kind === 'top' ? 'legacyTopCase' : 'legacyMemberCase';
result.actual = [0, -3, 7, -2147483648, 2147483647].map(seed => String(exported[method](seed)));
record(); assert.deepEqual(result.actual, result.expected);
guard(); result.passed = true; record();
console.log(`PASS unchanged historical ${kind} overload: original JVM/public CLI/host five pairs; explicit test consumer, no SDK claim`);
