// Run only in the integration owner's full-CLI build slot. Reuse real producers.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { existsSync, mkdtempSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../../..');
assert.ok(process.argv[2], 'Pass a completed focused r1 work directory');
const producer = resolve(process.argv[2]);
const work = mkdtempSync(join(producer, 'public-'));
console.log(`Evidence: ${work}`);
process.env.JAVA_TOOL_OPTIONS = '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC';
process.env.PATH = `/Applications/Android Studio.app/Contents/jbr/Contents/Home/bin:${process.env.PATH}`;
const cp = JSON.parse(readFileSync(join(producer, 'classpath.json'), 'utf8')).stdout.trim();
const hash = path => createHash('sha256').update(readFileSync(path)).digest('hex');
const sources = directory => readdirSync(directory, { withFileTypes: true }).flatMap(entry => entry.isDirectory()
  ? sources(join(directory, entry.name)) : entry.name.endsWith('.kt') ? [join(directory, entry.name)] : []);
const implementation = [join(root, 'kotlin-ets'), ...sources(join(root, 'src'))].sort().map(path => ({ path, sha256: hash(path) }));
const inputs = readdirSync(producer).filter(name => name.endsWith('.jar')).map(name => join(producer, name))
  .concat(sources(here)).map(path => ({ path, sha256: hash(path) }));
writeFileSync(join(work, 'identity.json'), JSON.stringify({ implementation, inputs }, null, 2));
function run(label, command, args, status = 0) {
  const result = spawnSync(command, args, { encoding: 'utf8', timeout: 300000 });
  writeFileSync(join(work, `${label}.json`), JSON.stringify({ command, args, status: result.status,
    stdout: result.stdout, stderr: result.stderr, error: result.error?.message }, null, 2));
  if (result.error) throw result.error;
  assert.equal(result.status, status, `${label}: ${result.stdout}\n${result.stderr}`);
  return result.stdout;
}
const compiler = join(root, 'tests/stdlib/compiler.sh');
const application = join(here, 'Application.kt');
const results = [];
for (const [name, jars] of [['same', ['same.jar']], ['cross-facade', ['combined.jar']], ['second-jar', ['entry.jar', 'helper.jar']]]) {
  const classpath = [cp, ...jars.map(jar => join(producer, jar))].join(':');
  const oracle = join(work, `${name}-oracle.jar`);
  run(`${name}-oracle-build`, 'bash', [compiler, '-classpath', classpath, application, join(here, 'Oracle.kt'), '-d', oracle]);
  const expected = run(`${name}-jvm`, 'java', ['-cp', `${classpath}:${oracle}`, 'consumer.OracleKt']).trim().split('\n');
  assert.deepEqual(expected, ['27/2/:1:2', '-15/2/:-2:-1', '-1/2/:2147483647:-2147483648']);
  const output = join(work, `${name}.ets`);
  run(`${name}-cli`, 'bash', [join(root, 'kotlin-ets'), '--mode', 'language', '--classpath', classpath, '--out', output, application]);
  const compiled = ts.transpileModule(readFileSync(output, 'utf8'), {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS }, reportDiagnostics: true,
  });
  assert.deepEqual(compiled.diagnostics, []);
  const context = { exports: {} };
  vm.runInNewContext(compiled.outputText, context, { timeout: 1000 });
  const actual = [1, -2, 2147483647].map(seed => context.exports.scenario(seed));
  results.push({ name, expected, actual, output, sha256: hash(output) });
  writeFileSync(join(work, 'runtime.json'), JSON.stringify(results, null, 2));
  assert.deepEqual(actual, expected);
}
for (const [name, jars, message] of [
  ['missing-body', ['entry.jar', 'signature-helper.jar'], /missing serialized IR body for dependency.*helper/],
  ['missing-jar', ['entry.jar'], /unlinked serialized dependencies:.*helper/],
  ['missing-source', ['entry.jar', 'no-source-helper.jar'], /no SourceFile attribute.*no-source-helper.jar/],
  ['cycle', ['cycle-entry.jar', 'cycle-helper.jar'], /serialized inline dependency cycle: entry -> helper -> entry/],
]) {
  const output = join(work, `${name}.ets`);
  const diagnostic = JSON.parse(run(`${name}-cli`, 'bash', [join(root, 'kotlin-ets'), '--mode', 'language',
    '--classpath', [cp, ...jars.map(jar => join(producer, jar))].join(':'), '--out', output, application], 2));
  assert.equal(diagnostic.code, 'UNSUPPORTED');
  assert.match(diagnostic.message, message);
  assert.equal(diagnostic.source.file, application);
  assert.ok(diagnostic.source.start >= 0 && diagnostic.source.end > diagnostic.source.start);
  assert.equal(existsSync(output), false);
}
assert.ok(implementation.every(item => hash(item.path) === item.sha256), 'Production changed during replay');
writeFileSync(join(work, 'complete.json'), JSON.stringify({ positiveCases: 3, negativeCases: 4, jvmTargetPairs: 9, implementationUnchanged: true }));
console.log('PASS public CLI: 9 JVM/target pairs, four closed dependency failures; no producer rebuild');
