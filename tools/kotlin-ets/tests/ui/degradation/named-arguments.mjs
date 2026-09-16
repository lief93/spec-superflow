import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {existsSync, mkdtempSync, readFileSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';

const launcher = fileURLToPath(new URL('../../../kotlin-ets', import.meta.url));
assert.ok(process.argv[2], 'provide a real Compose classpath.txt');
const root = mkdtempSync(join(tmpdir(), 'kotlin-ets-degradation-named-'));
for (const [entry, expected, failure = /SDK_INT/] of [
  ['NamedArguments', '0'], ['ExplicitLocal', '1'], ['UnsupportedNamedArgument', 'Skipped'],
  ['RequiredNamedArgument', null], ['UnsupportedType', ['Before', 'After']],
  ['ExplicitUnsupportedType', null, /fadeIn|EnterTransition/],
]) {
  const source = fileURLToPath(new URL(entry.endsWith('Type') ? './TypedArguments.kt' : './NamedArguments.kt', import.meta.url));
  const output = join(root, entry + '.ets');
  const result = spawnSync('bash', [launcher, '--entry', `degradation.${entry}`, '--classpath-file', process.argv[2],
    '--out', output, source], {encoding: 'utf8', maxBuffer: 20 * 1024 * 1024,
    env: {...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC'}});
  writeFileSync(join(root, entry + '.log'), result.stdout + result.stderr);
  assert.equal(result.status, expected === null ? 2 : 0, result.stdout + result.stderr);
  const report = JSON.parse(readFileSync(output + '.diagnosis.json', 'utf8'));
  if (expected === null) {
    assert.equal(report.status, 'blocked');
    assert.match(report.blockingFailure.message, failure);
    assert.equal(existsSync(output), false);
    console.log(`PASS ${entry}: required value or explicit source local still blocks`);
    continue;
  }
  assert.equal(report.degradationCount, 1);
  const code = readFileSync(output, 'utf8');
  // These fixtures contain only Text calls. Omit the native entry container;
  // execute the untouched ordinary functions and generated builder methods.
  const executable = code.slice(0, code.lastIndexOf('  build() {')).replace(/^import .*;\n/gm, '')
    .replace(/@(Entry|Component|Builder)\s*/g, '').replace('export struct ', 'export class ') + '}\n';
  const labels = [];
  const chain = new Proxy(() => {}, {get: () => chain, apply: () => chain});
  const context = vm.createContext({exports: {}, Text: value => {labels.push(value); return chain;}, Alignment: {TopStart: 0}});
  vm.runInContext(ts.transpileModule(executable, {compilerOptions: {
    target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS,
  }}).outputText, context);
  const page = new context.exports[entry]();
  page[entry]();
  assert.deepEqual(labels, Array.isArray(expected) ? expected : [expected], `${entry}: dropped compiler argument evaluation but kept explicit local evaluation`);
  console.log(`PASS ${entry}: ${labels}`);
}
console.log(JSON.stringify({ok: true, root}));
