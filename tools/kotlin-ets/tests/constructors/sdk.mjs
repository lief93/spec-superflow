import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { cpSync, copyFileSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { basename, dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { verifyModuleCoverage } from '../modules/ui-sdk-evidence.mjs';

const here = dirname(fileURLToPath(import.meta.url)), root = resolve(here, '../..');
assert.ok(process.argv[2], 'Pass successful module evidence; optionally an explicit SDK consumer');
const evidence = resolve(process.argv[2]);
const previous = JSON.parse(readFileSync(join(evidence, 'result.json'), 'utf8'));
assert.equal(previous.passed, true);
const hash = path => createHash('sha256').update(readFileSync(path)).digest('hex');
const consumer = process.argv[3] ? resolve(process.argv[3]) : join(here, 'SdkIndex.ets');
const ability = join(root, 'tests/language/SdkEntryAbility.ets');
const inputs = [...previous.inputs, ...[consumer, ability, fileURLToPath(import.meta.url),
  join(here, '../modules/ui-sdk-evidence.mjs')].map(path => ({ path, sha256: hash(path) }))];
const modules = previous.modules;
if (!process.argv[3]) assert.equal(modules.length, 6);
assert.ok(modules.length > 0);
for (const input of [...inputs, ...modules]) assert.equal(hash(input.path), input.sha256, input.path);
const sdk = '/Applications/DevEco-Studio.app/Contents';
const seed = process.env.KOTLIN_ETS_SDK_SEED ?? '/private/tmp/kotlin-ets-native-20260913-07/harmony';
const work = mkdtempSync('/private/tmp/kotlin-ets-constructors-sdk-'), host = join(work, 'harmony');
const result = { evidence, level: 'public Kotlin CLI output and SDK compilation, not native runtime or UI acceptance',
  inputs, modules, commands: [], passed: false };
const record = () => writeFileSync(join(work, 'result.json'), JSON.stringify(result, null, 2));
const env = { ...process.env, JAVA_HOME: join(sdk, 'jbr/Contents/Home'), DEVECO_SDK_HOME: join(sdk, 'sdk'),
  JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC',
  PATH: `${sdk}/tools/node/bin:${sdk}/tools/ohpm/bin:${process.env.PATH}` };
function run(label, command, args) {
  const r = spawnSync(command, args, { cwd: host, env, encoding: 'utf8', timeout: 600000, maxBuffer: 32 * 1024 * 1024 });
  writeFileSync(join(work, label + '.stdout'), r.stdout ?? ''); writeFileSync(join(work, label + '.stderr'), r.stderr ?? '');
  result.commands.push({ label, command, args, status: r.status }); record();
  assert.equal(r.error, undefined); assert.equal(r.status, 0, r.stdout + r.stderr);
}
console.log(`SDK evidence: ${work}`);
const excluded = new Set(['build', '.hvigor', 'oh_modules', '.idea', '.migration', '.git']);
cpSync(seed, host, { recursive: true, filter: path => !excluded.has(basename(path)) });
const ets = join(host, 'entry/src/main/ets');
rmSync(ets, { recursive: true, force: true });
for (const path of ['pages', 'entryability', 'modules']) mkdirSync(join(ets, path), { recursive: true });
copyFileSync(consumer, join(ets, 'pages/Index.ets'));
copyFileSync(ability, join(ets, 'entryability/EntryAbility.ets'));
writeFileSync(join(host, 'entry/src/main/resources/base/profile/main_pages.json'), JSON.stringify({ src: ['pages/Index'] }));
for (const input of modules) copyFileSync(input.path, join(ets, 'modules', input.name));
run('install', join(sdk, 'tools/ohpm/bin/ohpm'), ['install']);
run('sdk', join(sdk, 'tools/hvigor/bin/hvigorw'), ['assembleHap', '--mode', 'module', '-p', 'module=entry@default', '-p', 'product=default', '--no-daemon']);
const cache = join(host, 'entry/build/default/cache/default/default@CompileArkTS/esmodule');
const filesInfo = join(cache, 'debug/filesInfo.txt'), buildInfoPath = join(cache, '.tsbuildinfo'), checkerPath = join(cache, '.ts_checker_cache');
result.coverage = verifyModuleCoverage({ modules, ets, records: readFileSync(filesInfo, 'utf8').split('\n'), buildInfoPath,
  buildInfo: JSON.parse(readFileSync(buildInfoPath, 'utf8')), checker: JSON.parse(readFileSync(checkerPath, 'utf8')) });
result.checkerEvidence = [filesInfo, buildInfoPath, checkerPath].map(path => ({ path, sha256: hash(path) }));
const abc = join(host, 'entry/build/default/intermediates/loader_out/default/ets/modules.abc');
result.abc = { path: abc, sha256: hash(abc) };
const output = join(host, 'entry/build/default/outputs/default');
result.haps = readdirSync(output).filter(name => name.endsWith('.hap')).map(name => ({ path: join(output, name), sha256: hash(join(output, name)) }));
assert.ok(result.haps.length > 0);
for (const input of [...inputs, ...modules]) assert.equal(hash(input.path), input.sha256, input.path);
for (const input of modules) assert.equal(hash(join(ets, 'modules', input.name)), input.sha256);
assert.equal(hash(join(ets, 'pages/Index.ets')), hash(consumer));
assert.equal(hash(join(ets, 'entryability/EntryAbility.ets')), hash(ability));
result.passed = true; record(); console.log(`PASS ${modules.length} unchanged public Kotlin-to-ETS modules checked and compiled to SDK ABC/HAP`);
