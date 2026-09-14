import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { cpSync, copyFileSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync, readdirSync } from 'node:fs';
import { basename, dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const here = dirname(fileURLToPath(import.meta.url));
assert.ok(process.argv[2], 'Pass generated control ETS and optionally its media directory');
const input = resolve(process.argv[2]);
const seed = process.env.KOTLIN_ETS_SDK_SEED ?? '/private/tmp/kotlin-ets-native-20260914-06/harmony';
const sdk = '/Applications/DevEco-Studio.app/Contents';
const work = mkdtempSync('/private/tmp/kotlin-ets-basic-controls-sdk-');
const host = join(work, 'harmony');
const hash = path => createHash('sha256').update(readFileSync(path)).digest('hex');
const manifest = { input, sha256: hash(input), seed, host, commands: [], media: [], passed: false };
const record = () => writeFileSync(join(work, 'result.json'), JSON.stringify(manifest, null, 2));
console.log('SDK evidence: ' + work);
record();
const excluded = new Set(['build', '.hvigor', 'oh_modules', '.idea', '.migration', '.git']);
cpSync(seed, host, { recursive: true, filter: path => !excluded.has(basename(path)) });
const ets = join(host, 'entry/src/main/ets');
rmSync(ets, { recursive: true, force: true });
for (const name of ['pages', 'entryability']) mkdirSync(join(ets, name), { recursive: true });
const output = join(ets, 'pages/Index.ets');
copyFileSync(input, output);
copyFileSync(join(here, '../language/SdkEntryAbility.ets'), join(ets, 'entryability/EntryAbility.ets'));
writeFileSync(join(host, 'entry/src/main/resources/base/profile/main_pages.json'), JSON.stringify({ src: ['pages/Index'] }));
if (process.argv[3]) {
  const media = resolve(process.argv[3]);
  const destination = join(host, 'entry/src/main/resources/base/media');
  mkdirSync(destination, { recursive: true });
  for (const name of readdirSync(media)) {
    const path = join(media, name);
    copyFileSync(path, join(destination, name));
    manifest.media.push({ name, sha256: hash(path) });
  }
  record();
}
const env = { ...process.env, JAVA_HOME: join(sdk, 'jbr/Contents/Home'), DEVECO_SDK_HOME: join(sdk, 'sdk'),
  JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC',
  PATH: `${sdk}/tools/node/bin:${sdk}/tools/ohpm/bin:${process.env.PATH}` };
function run(label, command, args) {
  const result = spawnSync(command, args, { cwd: host, env, encoding: 'utf8', timeout: 300000, maxBuffer: 16 * 1024 * 1024 });
  writeFileSync(join(work, label + '.stdout'), result.stdout ?? '');
  writeFileSync(join(work, label + '.stderr'), result.stderr ?? '');
  manifest.commands.push({ label, status: result.status, error: result.error?.message });
  record();
  assert.equal(result.status, 0, (result.stdout ?? '') + (result.stderr ?? ''));
}
run('ohpm', join(sdk, 'tools/ohpm/bin/ohpm'), ['install']);
run('sdk', join(sdk, 'tools/hvigor/bin/hvigorw'),
  ['assembleHap', '--mode', 'module', '-p', 'module=entry@default', '-p', 'product=default', '--no-daemon']);
assert.equal(hash(input), manifest.sha256);
assert.equal(hash(output), manifest.sha256, 'Generated ETS must compile without patching');
const filesInfo = join(host, 'entry/build/default/cache/default/default@CompileArkTS/esmodule/debug/filesInfo.txt');
assert.match(readFileSync(filesInfo, 'utf8'), /pages\/Index\.ts;/);
manifest.abc = hash(join(host, 'entry/build/default/intermediates/loader_out/default/ets/modules.abc'));
manifest.haps = readdirSync(join(host, 'entry/build/default/outputs/default')).filter(name => name.endsWith('.hap'));
assert.ok(manifest.haps.length > 0);
manifest.passed = true;
record();
console.log(`PASS unmodified generated ${basename(input)} through actual SDK, ABC/HAP output; no install or visual run`);
