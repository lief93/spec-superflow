import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, writeFileSync, existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../..');
const work = mkdtempSync(join(tmpdir(), 'kotlin-ets-adapter-constructors-'));
console.log(`Evidence: ${work}`);
function run(name, command, args, expected = 0) {
  const result = spawnSync(command, args, { encoding: 'utf8', timeout: 600000,
    env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC',
      KOTLIN_ETS_ADAPTER_DIRS: join(here, 'module') } });
  writeFileSync(join(work, name + '.json'), JSON.stringify({ args, ...result }, null, 2));
  assert.equal(result.status, expected, result.stdout + result.stderr);
  return result.stdout;
}
const compiler = join(root, 'tests/stdlib/compiler.sh');
const cp = run('classpath', 'bash', [compiler, '--classpath']).trim();
const api = join(work, 'api.jar'), oracle = join(work, 'oracle.jar');
run('library', 'bash', [compiler, join(here, 'Api.kt'), '-d', api]);
run('oracle-compile', 'bash', [compiler, '-classpath', `${api}:${cp}`, join(here, 'Values.kt'),
  join(here, 'Oracle.kt'), '-d', oracle]);
const expected = run('oracle', 'java', ['-cp', `${api}:${oracle}:${cp}`, 'constructorvalues.OracleKt'])
  .trim().split('\n').map(Number);
function compile(name, status = 0) {
  const out = join(work, name + '.ets');
  const report = run(name, 'bash', [join(root, 'kotlin-ets'), '--mode', 'language', '--classpath',
    `${api}:${cp}`, '--out', out, join(here, name + '.kt')], status);
  assert.equal(existsSync(out), status === 0);
  return status === 0 ? readFileSync(out, 'utf8') : JSON.parse(report.trim().split('\n').at(-1));
}
const emitted = compile('Values');
const context = vm.createContext({ exports: {} });
vm.runInContext(ts.transpileModule(emitted, { compilerOptions: {
  target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS
} }).outputText, context);
const actual = Array.from(context.exports.observations());
assert.deepEqual(actual, expected);
assert.deepEqual(actual, [2.5, 2]);
assert.match(emitted, /new Source\(/);
for (const name of ['Wrong', 'Effect']) {
  const report = compile(name, 2);
  assert.match(report.message, /Invalid call adapter result/);
  assert.equal(resolve(report.source.file), join(here, name + '.kt'));
}
assert.match(compile('Unclaimed', 2).message, /Unsupported external constructor/);
const objects = compile('Objects');
const objectContext = vm.createContext({ exports: {} });
vm.runInContext(ts.transpileModule(objects, { compilerOptions: {
  target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS
} }).outputText, objectContext);
assert.equal(objectContext.exports.result(), 9);
for (const name of ['WrongObject', 'EffectObject']) {
  const report = compile(name, 2);
  assert.match(report.message, /Invalid call adapter result/);
  assert.equal(resolve(report.source.file), join(here, name + '.kt'));
}
writeFileSync(join(work, 'parity.json'), JSON.stringify({ expected, actual }, null, 2));
console.log('PASS constructor SPI, typed result rejection, source constructor and JVM once-only parity');
