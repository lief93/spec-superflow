import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { basename, dirname, join, resolve } from 'node:path';
import { cpSync, copyFileSync, existsSync, mkdirSync, mkdtempSync,
  readFileSync, rmSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const here = dirname(fileURLToPath(import.meta.url));
assert.ok(process.argv[2], 'Pass generated HelperEntry.ets');
const input = resolve(process.argv[2]);
const seed = process.env.KOTLIN_ETS_SDK_SEED ?? '/private/tmp/kotlin-ets-native-20260914-06/harmony';
const sdk = '/Applications/DevEco-Studio.app/Contents';
const work = mkdtempSync('/private/tmp/kotlin-ets-helper-sdk-');
const host = join(work, 'harmony');
const hash = path => createHash('sha256').update(readFileSync(path)).digest('hex');
const manifest = { input, sha256: hash(input), seed, host, commands: [], passed: false };
const record = () => writeFileSync(join(work, 'result.json'), JSON.stringify(manifest, null, 2));
console.log('SDK evidence: ' + work);
record();

const excluded = new Set(['build', '.hvigor', 'oh_modules', '.idea', '.migration', '.git']);
cpSync(seed, host, { recursive: true, filter: path => !excluded.has(basename(path)) });
const ets = join(host, 'entry/src/main/ets');
rmSync(ets, { recursive: true, force: true });
for (const name of ['pages', 'entryability', 'components']) mkdirSync(join(ets, name), { recursive: true });
const generated = join(ets, 'components/HelperEntry.ets');
copyFileSync(input, generated);
writeFileSync(join(ets, 'pages/Index.ets'), `import { HelperEntry } from '../components/HelperEntry';

@Entry
@Component
struct Index {
  build() {
    Column() {
      HelperEntry('title', 'slot', (): void => {})
    }
  }
}
`);
copyFileSync(join(here, '../../language/SdkEntryAbility.ets'), join(ets, 'entryability/EntryAbility.ets'));
writeFileSync(join(host, 'entry/src/main/resources/base/profile/main_pages.json'),
  JSON.stringify({ src: ['pages/Index'] }));

const env = { ...process.env, JAVA_HOME: join(sdk, 'jbr/Contents/Home'), DEVECO_SDK_HOME: join(sdk, 'sdk'),
  JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC',
  PATH: `${sdk}/tools/node/bin:${sdk}/tools/ohpm/bin:${process.env.PATH}` };
function run(label, command, args) {
  const result = spawnSync(command, args, { cwd: host, env, encoding: 'utf8', timeout: 300000,
    maxBuffer: 16 * 1024 * 1024 });
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
assert.equal(hash(generated), manifest.sha256, 'Generated ETS must compile without patching');
const filesInfo = join(host, 'entry/build/default/cache/default/default@CompileArkTS/esmodule/debug/filesInfo.txt');
const compiled = readFileSync(filesInfo, 'utf8');
assert.match(compiled, /pages\/Index\.ts;/);
assert.match(compiled, /components\/HelperEntry\.ts;/);
const abc = join(host, 'entry/build/default/intermediates/loader_out/default/ets/modules.abc');
assert.ok(existsSync(abc));
manifest.abc = hash(abc);
manifest.passed = true;
record();
console.log('PASS unmodified generated composable-helper ETS through actual SDK with typed host invocation');
