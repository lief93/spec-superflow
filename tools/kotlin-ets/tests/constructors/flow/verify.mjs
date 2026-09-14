import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { cpSync, copyFileSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { basename, dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';

const here = dirname(fileURLToPath(import.meta.url)), root = resolve(here, '../../..');
const testJar = resolve(process.argv[2]);
const work = mkdtempSync('/private/tmp/kotlin-ets-constructor-flow-'), host = join(work, 'harmony');
const sdk = '/Applications/DevEco-Studio.app/Contents';
const hash = path => createHash('sha256').update(readFileSync(path)).digest('hex');
function files(path) { return readdirSync(path, { withFileTypes: true }).flatMap(e => e.isDirectory() ? files(join(path, e.name)) : [join(path, e.name)]); }
const inputs = [...files(join(root, 'src/target')), ...files(join(root, 'tests/target')), ...files(here), testJar]
  .map(path => ({ path, sha256: hash(path) }));
const result = { level: 'typed target fixture, JVM/host parity and SDK compilation; not public Kotlin CLI conversion or native runtime acceptance', inputs, commands: [] };
const record = () => writeFileSync(join(work, 'result.json'), JSON.stringify(result, null, 2));
const env = { ...process.env, JAVA_HOME: join(sdk, 'jbr/Contents/Home'), DEVECO_SDK_HOME: join(sdk, 'sdk'),
  PATH: `${sdk}/tools/node/bin:${sdk}/tools/ohpm/bin:${process.env.PATH}` };
function run(label, command, args, cwd = root) {
  const r = spawnSync(command, args, { cwd, env, encoding: 'utf8', timeout: 300000, maxBuffer: 16 * 1024 * 1024 });
  writeFileSync(join(work, label + '.stdout'), r.stdout ?? ''); writeFileSync(join(work, label + '.stderr'), r.stderr ?? '');
  result.commands.push({ label, command, args, cwd, status: r.status }); record();
  assert.equal(r.error, undefined); assert.equal(r.status, 0, r.stdout + r.stderr);
  return r.stdout;
}
console.log(`Evidence: ${work}`);
const compiler = join(root, 'tests/stdlib/compiler.sh');
const cp = run('classpath', 'bash', [compiler, '--classpath']).trim();
const output = join(work, 'ConstructorFlow.ets');
run('target-tree', 'java', ['-cp', `${testJar}:${cp}`, 'dev.ets.ConstructorFlowTestKt', output]);
result.output = { path: output, sha256: hash(output) };
const code = readFileSync(output, 'utf8'), check = join(work, 'ConstructorFlow.ts');
writeFileSync(check, code);
const program = ts.createProgram([check], { strict: true, noEmit: true, types: [], target: ts.ScriptTarget.ES2022 });
assert.deepEqual(ts.getPreEmitDiagnostics(program).map(d => ts.flattenDiagnosticMessageText(d.messageText, '\n')), []);
const context = vm.createContext({ exports: {} });
vm.runInContext(ts.transpileModule(code, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } }).outputText, context);
result.actual = [0, 1].flatMap(mode => [-3, 0, 7].map(seed => String(context.exports.constructorResult(mode, seed))));
const oracle = join(work, 'oracle.jar');
run('jvm-build', 'bash', [compiler, join(here, 'Oracle.kt'), '-d', oracle]);
result.expected = run('jvm-run', 'java', ['-cp', `${oracle}:${cp}`, 'constructorflow.OracleKt']).trim().split('\n');
assert.deepEqual(result.actual, result.expected);
const excluded = new Set(['build', '.hvigor', 'oh_modules', '.idea', '.migration', '.git']);
cpSync('/private/tmp/kotlin-ets-native-20260913-07/harmony', host, { recursive: true, filter: path => !excluded.has(basename(path)) });
rmSync(join(host, 'entry/src/main/ets'), { recursive: true, force: true });
for (const path of ['pages', 'entryability']) mkdirSync(join(host, 'entry/src/main/ets', path), { recursive: true });
const copy = join(host, 'entry/src/main/ets/ConstructorFlow.ets');
copyFileSync(output, copy);
copyFileSync(join(root, 'tests/language/SdkEntryAbility.ets'), join(host, 'entry/src/main/ets/entryability/EntryAbility.ets'));
writeFileSync(join(host, 'entry/src/main/ets/pages/Index.ets'), `import { constructorResult } from '../ConstructorFlow';
@Entry
@Component
struct Index {
  build() { Text(constructorResult(0, 4).toString() + ':' + constructorResult(1, 4).toString()) }
}
`);
writeFileSync(join(host, 'entry/src/main/resources/base/profile/main_pages.json'), JSON.stringify({ src: ['pages/Index'] }));
run('install', join(sdk, 'tools/ohpm/bin/ohpm'), ['install'], host);
run('sdk', join(sdk, 'tools/hvigor/bin/hvigorw'), ['assembleHap', '--mode', 'module', '-p', 'module=entry@default', '-p', 'product=default', '--no-daemon'], host);
const compilerFiles = readFileSync(join(host, 'entry/build/default/cache/default/default@CompileArkTS/esmodule/debug/filesInfo.txt'), 'utf8');
writeFileSync(join(work, 'filesInfo.txt'), compilerFiles);
assert.ok(compilerFiles.split('\n').some(line => line.includes('/ConstructorFlow.ts;') && line.endsWith(';ets')));
const abc = join(host, 'entry/build/default/intermediates/loader_out/default/ets/modules.abc');
result.abc = { path: abc, sha256: hash(abc) };
const haps = join(host, 'entry/build/default/outputs/default');
result.haps = readdirSync(haps).filter(name => name.endsWith('.hap')).map(name => ({ path: join(haps, name), sha256: hash(join(haps, name)) }));
assert.ok(result.haps.length > 0);
assert.equal(hash(output), result.output.sha256); assert.equal(hash(copy), result.output.sha256);
for (const input of inputs) assert.equal(hash(input.path), input.sha256, input.path);
result.passed = true; record(); console.log('PASS six JVM/ETS-host results and unchanged typed-target ETS in SDK ABC/HAP');
