import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, writeFileSync, existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';
const here = dirname(fileURLToPath(import.meta.url)), root = resolve(here, '../../..');
const work = mkdtempSync(join(tmpdir(), 'kotlin-ets-material-button-'));
console.log('Evidence: ' + work);
const cp = JSON.parse(readFileSync('/tmp/kotlin-official-frontend-probe-06/classpath.json')).filter(existsSync);
const cpFile = join(work, 'classpath.txt');
writeFileSync(cpFile, cp.join('\n'));
function run(label, command, args, status = 0) {
  const result = spawnSync(command, args, { encoding: 'utf8', timeout: 600000,
    env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' } });
  writeFileSync(join(work, label + '.json'), JSON.stringify({ args, ...result }, null, 2));
  assert.equal(result.status, status, result.stdout + result.stderr);
  return result.stdout;
}
const model = join(work, 'Models.ets');
run('models', 'bash', [join(root, 'kotlin-ets'), '--mode', 'language', '--classpath-file', cpFile,
  '--out', model, join(here, 'Models.kt')]);
const context = vm.createContext({ exports: {} });
vm.runInContext(ts.transpileModule(readFileSync(model, 'utf8'), { compilerOptions: {
  target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS
} }).outputText, context);
const actual = Array.from(context.exports.observations());
context.exports.count = 0;
const edge = context.exports.edges();
actual.push(edge.left, edge.top, edge.right, edge.bottom, context.exports.count);
actual.push(context.exports.uniform().top, context.exports.count);
const jar = join(work, 'oracle.jar');
run('jvm-build', 'bash', [join(root, 'tests/stdlib/compiler.sh'), '-classpath', cp.join(':'),
  join(here, 'Models.kt'), join(here, 'Oracle.kt'), '-d', jar]);
const expected = run('jvm', 'java', ['-cp', [jar, ...cp].join(':'), 'materialbutton.OracleKt']).trim().split('\n').map(Number);
assert.deepEqual(actual, expected);
writeFileSync(join(work, 'parity.json'), JSON.stringify({ actual, expected }));
for (const [entry, status] of [['Page', 0], ['UnsupportedInteraction', 2], ['UnsupportedReceiver', 2], ['UnsupportedTextReceiver', 2]]) {
  const out = join(work, entry + '.ets');
  const result = run(entry, 'bash', [join(root, 'kotlin-ets'), '--entry', 'materialbutton.' + entry,
    '--classpath-file', cpFile, '--out', out, join(here, 'Page.kt')], status);
  assert.equal(existsSync(out), status === 0);
  if (status) assert.match(result, entry === 'UnsupportedInteraction' ? /interactionSource/ : /Bind ButtonDefaults receiver/);
  else {
    const code = readFileSync(out, 'utf8');
    assert.match(code, /colors: EtsButtonColors/);
    assert.match(code, /\.disabledContainerColor/);
    assert.match(code, /\.disabledContentColor/);
    assert.match(code, /__etsUniformPadding\(16(?:\.0)?\)/);
    assert.match(code, /new EtsShape\("rounded", 12(?:\.0)?, 12(?:\.0)?, 12(?:\.0)?, 12(?:\.0)?\)/);
    assert.match(code, /\.borderRadius\(\{ topLeft: uiTemporary\d+_\d+\.topStart, topRight: uiTemporary\d+_\d+\.topEnd, bottomRight: uiTemporary\d+_\d+\.bottomEnd, bottomLeft: uiTemporary\d+_\d+\.bottomStart \}\)/);
    assert.match(code, /\.borderRadius\([^\n]+\)\.clip\(true\)/);
    assert.match(code, /\.border\(\{ width: uiTemporary\d+_\d+\.width, color: uiTemporary\d+_\d+\.color, radius: \{ topLeft: [^}]+ \} \}\)/);
    assert.match(code, /\.enabled\(enabled\)/);
  }
}
console.log('PASS ButtonColors JVM parity, source parameters, material button states and rejected interactions');
