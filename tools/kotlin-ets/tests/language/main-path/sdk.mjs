import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { cpSync, copyFileSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { basename, dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

export function verifySdk(here, evidencePath, suite) {
assert.ok(evidencePath, 'Pass successful language runner evidence');
const evidence = resolve(evidencePath);
const previous = JSON.parse(readFileSync(join(evidence, 'result.json')));
assert.equal(previous.passed, true);
const hash = path => createHash('sha256').update(readFileSync(path)).digest('hex');
const modules = previous.outputs.filter(input => dirname(input.path) === join(evidence, 'modules'));
assert.ok(modules.length > 0);
const inputs = [...previous.inputs, ...modules, fileURLToPath(import.meta.url), join(here, 'SdkIndex.ets'),
  join(here, '../SdkEntryAbility.ets')].map(input => typeof input === 'string' ? { path: input, sha256: hash(input) } : input);
for (const input of inputs) assert.equal(hash(input.path), input.sha256);
const sdk = '/Applications/DevEco-Studio.app/Contents';
const seed = process.env.KOTLIN_ETS_SDK_SEED ?? '/private/tmp/kotlin-ets-native-20260913-07/harmony';
const work = mkdtempSync(`/private/tmp/kotlin-ets-${suite}-sdk-`), host = join(work, 'harmony');
const manifest = { evidence, seed, host, inputs, commands: [], passed: false, level: 'actual ArkTS SDK compile; not native execution' };
const record = () => writeFileSync(join(work, 'manifest.json'), JSON.stringify(manifest, null, 2));
const env = { ...process.env, JAVA_HOME: join(sdk, 'jbr/Contents/Home'), DEVECO_SDK_HOME: join(sdk, 'sdk'),
  JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC',
  PATH: `${sdk}/tools/node/bin:${sdk}/tools/ohpm/bin:${process.env.PATH}` };
function run(label, command, args) {
  const result = spawnSync(command, args, { cwd: host, env, encoding: 'utf8', timeout: 600000, maxBuffer: 32 * 1024 * 1024 });
  writeFileSync(join(work, label + '.stdout'), result.stdout ?? '');
  writeFileSync(join(work, label + '.stderr'), result.stderr ?? '');
  manifest.commands.push({ label, command, args, status: result.status, error: result.error?.message }); record();
  assert.equal(result.error, undefined); assert.equal(result.status, 0, result.stdout + result.stderr);
}
console.log(`SDK evidence: ${work}`); record();
const excluded = new Set(['build', '.hvigor', 'oh_modules', '.idea', '.migration', '.git']);
cpSync(seed, host, { recursive: true, filter: path => !excluded.has(basename(path)) });
const ets = join(host, 'entry/src/main/ets');
rmSync(ets, { recursive: true, force: true });
for (const directory of ['pages', 'entryability', 'modules']) mkdirSync(join(ets, directory), { recursive: true });
copyFileSync(join(here, 'SdkIndex.ets'), join(ets, 'pages/Index.ets'));
copyFileSync(join(here, '../SdkEntryAbility.ets'), join(ets, 'entryability/EntryAbility.ets'));
writeFileSync(join(host, 'entry/src/main/resources/base/profile/main_pages.json'), JSON.stringify({ src: ['pages/Index'] }));
for (const input of modules) copyFileSync(input.path, join(ets, 'modules', basename(input.path)));
run('ohpm-install', join(sdk, 'tools/ohpm/bin/ohpm'), ['install']);
run('sdk-assemble', join(sdk, 'tools/hvigor/bin/hvigorw'),
  ['assembleHap', '--mode', 'module', '-p', 'module=entry@default', '-p', 'product=default', '--no-daemon']);
for (const input of inputs) assert.equal(hash(input.path), input.sha256);
for (const input of modules) assert.equal(hash(join(ets, 'modules', basename(input.path))), input.sha256);
const filesInfo = join(host, 'entry/build/default/cache/default/default@CompileArkTS/esmodule/debug/filesInfo.txt');
const records = readFileSync(filesInfo, 'utf8').split('\n');
manifest.compiledModules = modules.map(input => {
  const name = basename(input.path, '.ets');
  const record = records.find(line => line.includes(`/modules/${name}.ts;`) && line.endsWith(';ets'));
  assert.ok(record, `Missing actual ETS SDK input: ${name}`); return record;
});
const abc = join(host, 'entry/build/default/intermediates/loader_out/default/ets/modules.abc');
manifest.abc = { path: abc, sha256: hash(abc) };
const outputs = join(host, 'entry/build/default/outputs/default');
manifest.haps = readdirSync(outputs).filter(name => name.endsWith('.hap')).map(name => ({ path: join(outputs, name), sha256: hash(join(outputs, name)) }));
assert.ok(manifest.haps.length > 0); manifest.passed = true; record();
console.log(`PASS actual ArkTS SDK: ${modules.length} unchanged ${suite} modules, ABC and HAP outputs`);

}
