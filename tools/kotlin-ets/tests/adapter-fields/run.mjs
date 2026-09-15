import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, readFileSync, writeFileSync, existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';
const here = dirname(fileURLToPath(import.meta.url)), root = resolve(here, '../..');
const work = mkdtempSync(join(tmpdir(), 'kotlin-ets-adapter-fields-'));
console.log(`Evidence: ${work}`);
function run(name, command, args, expected = 0) {
  const result = spawnSync(command, args, { encoding: 'utf8', timeout: 600000,
    env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC',
      KOTLIN_ETS_ADAPTER_DIRS: join(here, 'module') } });
  writeFileSync(join(work, name + '.json'), JSON.stringify({ args, ...result }, null, 2));
  assert.equal(result.status, expected, result.stdout + result.stderr);
  return result.stdout;
}
const classes = join(work, 'classes'); mkdirSync(classes);
run('javac', '/Applications/Android Studio.app/Contents/jbr/Contents/Home/bin/javac', ['-d', classes, join(here, 'Api.java')]);
const cp = run('classpath', 'bash', [join(root, 'tests/stdlib/compiler.sh'), '--classpath']).trim();
for (const [entry, message] of [['value', null], ['wrong', /Invalid call adapter result/],
  ['effect', /Invalid call adapter result/], ['unclaimed', /Unsupported external field: fieldapi.Api.unclaimed/],
  ['write', /Unsupported external field assignment/]]) {
  const out = join(work, entry + '.ets');
  const report = run(entry, 'bash', [join(root, 'kotlin-ets'), '--mode', 'language', '--entry', 'fieldvalues.' + entry,
    '--classpath', `${classes}:${cp}`, '--out', out, join(here, 'Values.kt')], message ? 2 : 0);
  assert.equal(existsSync(out), !message);
  if (message) assert.match(report, message);
  else {
    const context = vm.createContext({ exports: {} });
    vm.runInContext(ts.transpileModule(readFileSync(out, 'utf8'), { compilerOptions: {
      target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } }).outputText, context);
    assert.equal(context.exports.value(), 11);
  }
}
console.log('PASS typed field SPI, wrong/void rejection, unclaimed reads, write diagnostics and source field regression');
