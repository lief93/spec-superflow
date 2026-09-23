import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';

const here = dirname(fileURLToPath(import.meta.url)), root = resolve(here, '../../..');
const work = mkdtempSync(join(tmpdir(), 'kotlin-ets-object-interfaces-'));
const java = '/Applications/Android Studio.app/Contents/jbr/Contents/Home';
const env = { ...process.env, JAVA_HOME: java, PATH: `${java}/bin:${process.env.PATH}`,
  JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' };
console.log(`Evidence: ${work}`);
function run(name, command, args) {
  const result = spawnSync(command, args, { env, encoding: 'utf8', timeout: 600000 });
  writeFileSync(join(work, name + '.json'), JSON.stringify({ args, ...result }, null, 2));
  assert.equal(result.status, 0, result.stdout + result.stderr);
  return result.stdout.trim();
}
const compiler = join(root, 'tests/stdlib/compiler.sh');
const cp = run('classpath', 'bash', [compiler, '--classpath']);
const jar = join(work, 'oracle.jar');
run('compile-jvm', 'bash', [compiler, join(here, 'Program.kt'), join(here, 'Oracle.kt'), '-d', jar]);
const expected = run('jvm', `${java}/bin/java`, ['-cp', `${cp}:${jar}`, 'objectinterfaces.OracleKt']).split('\n');
assert.deepEqual(expected, ['consumed', 'triggered', 'true', 'complete', 'true']);
const output = join(work, 'Program.ets');
run('compile-ets', 'bash', [join(root, 'kotlin-ets'), '--mode', 'language', '--classpath', cp,
  '--out', output, join(here, 'Program.kt')]);
const code = readFileSync(output, 'utf8');
const context = vm.createContext({ exports: {} });
vm.runInContext(ts.transpileModule(code, { compilerOptions: { target: ts.ScriptTarget.ES2022,
  module: ts.ModuleKind.CommonJS } }).outputText, context);
assert.deepEqual(['defaultEvent', 'triggeredEvent', 'sameInstance', 'sealedObjectLabel', 'sealedObjectIdentity']
  .map(name => String(context.exports[name]())), expected);
console.log('PASS JVM/ETS singleton interfaces and sealed-class inheritance: dispatch and identity');
