import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { cpSync, copyFileSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { basename, dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { verifyModuleCoverage } from '../ui-sdk-evidence.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../../..');
assert.ok(process.argv[2], 'Pass successful generic-heritage/run.mjs evidence after main freeze and SDK slot grant');
const evidence = resolve(process.argv[2]);
const previous = JSON.parse(readFileSync(join(evidence, 'result.json'), 'utf8'));
assert.equal(previous.passed, true);
const hash = path => createHash('sha256').update(readFileSync(path)).digest('hex');
for (const input of previous.inputs) {
  assert.equal(hash(input.path), input.sha256, `Source changed since generation: ${input.path}`);
  assert.equal(hash(input.snapshot), input.sha256);
}
const modules = previous.modules.map(input => ({ ...input, path: join(previous.output, input.name) }));
for (const input of modules) assert.equal(hash(input.path), input.sha256);
assert.deepEqual(readdirSync(previous.output).sort(), modules.map(input => input.name).sort());
const sdk = '/Applications/DevEco-Studio.app/Contents';
const seed = process.env.KOTLIN_ETS_SDK_SEED ?? '/private/tmp/kotlin-ets-native-20260913-07/harmony';
const work = mkdtempSync('/private/tmp/kotlin-ets-generic-heritage-sdk-');
const host = join(work, 'harmony');
const consumer = join(here, 'Index.ets');
const ability = join(root, 'tests/language/SdkEntryAbility.ets');
const manifest = { evidence, seed, host, inputs: previous.inputs, modules,
  consumer: { path: consumer, sha256: hash(consumer) }, ability: { path: ability, sha256: hash(ability) },
  verifier: [fileURLToPath(import.meta.url), join(here, '../ui-sdk-evidence.mjs')].map(path => ({ path, sha256: hash(path) })),
  commands: [], passed: false };
const record = () => writeFileSync(join(work, 'manifest.json'), JSON.stringify(manifest, null, 2));
const env = { ...process.env, JAVA_HOME: join(sdk, 'jbr/Contents/Home'), DEVECO_SDK_HOME: join(sdk, 'sdk'),
  JAVA_TOOL_OPTIONS: `${process.env.JAVA_TOOL_OPTIONS ?? ''} -XX:ActiveProcessorCount=2 -XX:+UseSerialGC`.trim(),
  PATH: `${sdk}/tools/node/bin:${sdk}/tools/ohpm/bin:${process.env.PATH}` };
function run(label, command, args) {
  const result = spawnSync(command, args, { cwd: host, env, encoding: 'utf8', timeout: 600000, maxBuffer: 32 * 1024 * 1024 });
  writeFileSync(join(work, `${label}.stdout`), result.stdout ?? '');
  writeFileSync(join(work, `${label}.stderr`), result.stderr ?? '');
  manifest.commands.push({ label, command, args, status: result.status, error: result.error?.message });
  record();
  assert.equal(result.error, undefined);
  assert.equal(result.status, 0, result.stdout + result.stderr);
}
console.log(`SDK evidence: ${work}`);
record();
const excluded = new Set(['build', '.hvigor', 'oh_modules', '.idea', '.migration', '.git']);
cpSync(seed, host, { recursive: true, filter: path => !excluded.has(basename(path)) });
const ets = join(host, 'entry/src/main/ets');
rmSync(ets, { recursive: true, force: true });
for (const directory of ['pages', 'entryability', 'modules']) mkdirSync(join(ets, directory), { recursive: true });
copyFileSync(consumer, join(ets, 'pages/Index.ets'));
copyFileSync(ability, join(ets, 'entryability/EntryAbility.ets'));
writeFileSync(join(host, 'entry/src/main/resources/base/profile/main_pages.json'), JSON.stringify({ src: ['pages/Index'] }));
for (const input of modules) copyFileSync(input.path, join(ets, 'modules', input.name));
run('ohpm-install', join(sdk, 'tools/ohpm/bin/ohpm'), ['install']);
run('sdk-assemble', join(sdk, 'tools/hvigor/bin/hvigorw'),
  ['assembleHap', '--mode', 'module', '-p', 'module=entry@default', '-p', 'product=default', '--no-daemon']);
for (const input of [...previous.inputs, manifest.consumer, manifest.ability, ...manifest.verifier, ...modules]) {
  assert.equal(hash(input.path), input.sha256);
}
assert.equal(hash(join(ets, 'pages/Index.ets')), manifest.consumer.sha256);
assert.equal(hash(join(ets, 'entryability/EntryAbility.ets')), manifest.ability.sha256);
for (const input of modules) assert.equal(hash(join(ets, 'modules', input.name)), input.sha256);
const cache = join(host, 'entry/build/default/cache/default/default@CompileArkTS/esmodule');
const filesInfo = join(cache, 'debug/filesInfo.txt');
const buildInfoPath = join(cache, '.tsbuildinfo');
const checkerPath = join(cache, '.ts_checker_cache');
manifest.moduleCoverage = verifyModuleCoverage({ modules, ets, records: readFileSync(filesInfo, 'utf8').split('\n'), buildInfoPath,
  buildInfo: JSON.parse(readFileSync(buildInfoPath, 'utf8')), checker: JSON.parse(readFileSync(checkerPath, 'utf8')) });
assert.deepEqual(manifest.moduleCoverage.filter(module => module.kind === 'interface-only').map(module => module.name), ['Readable.ets']);
manifest.checkerEvidence = [filesInfo, buildInfoPath, checkerPath].map(path => ({ path, sha256: hash(path) }));
const abc = join(host, 'entry/build/default/intermediates/loader_out/default/ets/modules.abc');
manifest.abc = { path: abc, sha256: hash(abc) };
const outputs = join(host, 'entry/build/default/outputs/default');
manifest.haps = readdirSync(outputs).filter(name => name.endsWith('.hap')).map(name => ({
  path: join(outputs, name), sha256: hash(join(outputs, name)),
}));
assert.ok(manifest.haps.length > 0);
manifest.passed = true;
record();
console.log(`PASS actual ETS SDK: ${modules.length} unchanged generic heritage modules, checked runtime/interface-only inputs and ABC/HAP output`);
