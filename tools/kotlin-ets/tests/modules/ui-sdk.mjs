import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { cpSync, copyFileSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { basename, dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { verifyModuleCoverage } from './ui-sdk-evidence.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../..');
const verifyOnly = process.argv[2] === '--verify-existing';
assert.ok(process.argv[verifyOnly ? 3 : 2], 'Pass ui-contract evidence, or --verify-existing <SDK evidence>');
const existingWork = verifyOnly ? resolve(process.argv[3]) : null;
const existing = verifyOnly ? JSON.parse(readFileSync(join(existingWork, 'manifest.json'), 'utf8')) : null;
if (verifyOnly) assert.ok(existing.commands.some(command => command.label === 'sdk-assemble' && command.status === 0 && !command.error),
  'Existing SDK build did not succeed');
const evidence = verifyOnly ? existing.evidence : resolve(process.argv[2]);
const previous = JSON.parse(readFileSync(join(evidence, 'result.json'), 'utf8'));
assert.equal(previous.passed, true);
const hash = path => createHash('sha256').update(readFileSync(path)).digest('hex');
for (const input of previous.inputs) {
  assert.equal(hash(input.path), input.sha256, `Source changed since target fixture generation: ${input.path}`);
  assert.equal(hash(input.snapshot), input.sha256);
}
const sdk = '/Applications/DevEco-Studio.app/Contents';
const seed = existing?.seed ?? process.env.KOTLIN_ETS_SDK_SEED ?? '/private/tmp/kotlin-ets-native-20260913-07/harmony';
const work = existingWork ?? mkdtempSync('/private/tmp/kotlin-ets-ui-modules-sdk-');
const host = existing?.host ?? join(work, 'harmony');
const consumer = join(here, 'UiSdkIndex.ets');
const ability = join(root, 'tests/language/SdkEntryAbility.ets');
const modules = previous.modules.map(input => ({ ...input, path: join(previous.output, input.name) }));
for (const input of modules) assert.equal(hash(input.path), input.sha256);
assert.deepEqual(readdirSync(previous.output).sort(), modules.map(input => input.name).sort());
const manifest = existing ? { ...existing, passed: false, verificationOnly: true } : { evidence, seed, host, inputs: previous.inputs, modules,
  consumer: { path: consumer, sha256: hash(consumer) }, ability: { path: ability, sha256: hash(ability) },
  commands: [], passed: false };
if (existing) {
  assert.deepEqual(existing.inputs, previous.inputs);
  assert.deepEqual(existing.modules, modules);
}
const record = () => writeFileSync(join(work, verifyOnly ? 'verification.json' : 'manifest.json'), JSON.stringify(manifest, null, 2));
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
console.log(`${verifyOnly ? 'Rechecking existing SDK evidence without a build' : 'SDK evidence'}: ${work}`);
record();
const ets = join(host, 'entry/src/main/ets');
if (!verifyOnly) {
  const excluded = new Set(['build', '.hvigor', 'oh_modules', '.idea', '.migration', '.git']);
  cpSync(seed, host, { recursive: true, filter: path => !excluded.has(basename(path)) });
  rmSync(ets, { recursive: true, force: true });
  for (const directory of ['pages', 'entryability', 'modules']) mkdirSync(join(ets, directory), { recursive: true });
  copyFileSync(consumer, join(ets, 'pages/Index.ets'));
  copyFileSync(ability, join(ets, 'entryability/EntryAbility.ets'));
  writeFileSync(join(host, 'entry/src/main/resources/base/profile/main_pages.json'), JSON.stringify({ src: ['pages/Index'] }));
  for (const input of modules) copyFileSync(input.path, join(ets, 'modules', input.name));
  run('ohpm-install', join(sdk, 'tools/ohpm/bin/ohpm'), ['install']);
  run('sdk-assemble', join(sdk, 'tools/hvigor/bin/hvigorw'),
    ['assembleHap', '--mode', 'module', '-p', 'module=entry@default', '-p', 'product=default', '--no-daemon']);
}
for (const input of [...previous.inputs, manifest.consumer, manifest.ability, ...modules]) assert.equal(hash(input.path), input.sha256);
assert.equal(hash(join(ets, 'pages/Index.ets')), manifest.consumer.sha256);
assert.equal(hash(join(ets, 'entryability/EntryAbility.ets')), manifest.ability.sha256);
for (const input of modules) assert.equal(hash(join(ets, 'modules', input.name)), input.sha256);
const filesInfo = join(host, 'entry/build/default/cache/default/default@CompileArkTS/esmodule/debug/filesInfo.txt');
const records = readFileSync(filesInfo, 'utf8').split('\n');
const buildInfoPath = join(dirname(dirname(filesInfo)), '.tsbuildinfo');
const checkerPath = join(dirname(buildInfoPath), '.ts_checker_cache');
manifest.moduleCoverage = verifyModuleCoverage({ modules, ets, records, buildInfoPath,
  buildInfo: JSON.parse(readFileSync(buildInfoPath, 'utf8')), checker: JSON.parse(readFileSync(checkerPath, 'utf8')) });
manifest.compiledModules = manifest.moduleCoverage.filter(module => module.kind === 'runtime').map(module => module.record);
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
console.log(`PASS actual ETS SDK coverage: ${modules.length} unchanged modules (${manifest.compiledModules.length} runtime, ` +
  `${manifest.moduleCoverage.filter(module => module.kind === 'interface-only').length} interface-only checked dependencies), ABC/HAP output`);
