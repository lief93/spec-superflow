import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {mkdtempSync, readFileSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';
const file = name => fileURLToPath(new URL(name, import.meta.url));
const root = mkdtempSync(join(tmpdir(), 'kotlin-ets-long-values-'));
console.log(root);
function run(name, command, args) {
  const result = spawnSync(command, args, {encoding: 'utf8', maxBuffer: 20 * 1024 * 1024,
    env: {...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC'}});
  writeFileSync(join(root, name + '.log'), result.stdout + result.stderr);
  assert.equal(result.status, 0, result.stdout + result.stderr);
  return result.stdout;
}
const compiler = file('../../stdlib/compiler.sh');
const cp = run('classpath', 'bash', [compiler, '--classpath']).trim();
run('oracle-build', 'bash', [compiler, file('Values.kt'), file('Oracle.kt'), '-d', join(root, 'oracle.jar')]);
const expected = run('oracle', 'java', ['-cp', cp + ':' + join(root, 'oracle.jar'), 'longvalues.OracleKt']).trim().split('\n');
run('generate', 'bash', [file('../../../kotlin-ets'), '--mode', 'language', '--entry', 'longvalues.observations',
  '--out', join(root, 'Values.ets'), file('Values.kt')]);
const context = vm.createContext({exports: {}});
const code = readFileSync(join(root, 'Values.ets'), 'utf8');
vm.runInContext(ts.transpileModule(code, {compilerOptions: {target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS}}).outputText, context);
assert.deepEqual(Array.from(context.exports.observations()), expected);
assert.match(code, /9007199254740993n/);
assert.match(code, /id: bigint/);
console.log(JSON.stringify({ok: true, root, expected, level: 'JVM versus ETS host execution'}));
