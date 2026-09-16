import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {mkdtempSync, readFileSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';
const launcher = fileURLToPath(new URL('../../kotlin-ets', import.meta.url));
const source = fileURLToPath(new URL('./DataMembers.kt', import.meta.url));
const root = mkdtempSync(join(tmpdir(), 'kotlin-ets-data-members-'));
for (const [entry, expected] of [['readOnly', 7], ['rendered', 'Label(value=kept)'], ['interpolated', 'label=Label(value=kept)'], ['compared', true], ['mixed', 'READY:7:Label(value=kept)'], ['unsupportedGeneric', null]]) {
  const output = join(root, entry + '.ets');
  const result = spawnSync('bash', [launcher, '--mode', 'language', '--entry', 'datamembers.' + entry,
    '--out', output, source], {encoding: 'utf8', maxBuffer: 20 * 1024 * 1024,
    env: {...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC'}});
  writeFileSync(output + '.log', result.stdout + result.stderr);
  assert.equal(result.status, expected === null ? 2 : 0, result.stdout + result.stderr);
  if (expected === null) {
    assert.match(result.stdout, /Unsupported string concatenation operand/);
  } else {
    const code = readFileSync(output, 'utf8');
    const context = vm.createContext({exports: {}});
    vm.runInContext(ts.transpileModule(code, {compilerOptions: {target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS}}).outputText, context);
    assert.equal(context.exports[entry](), expected);
    if (entry === 'readOnly') assert.doesNotMatch(code, /toString\(|hashCode\(|equals\(/);
  }
}
console.log(JSON.stringify({ok: true, root}));
