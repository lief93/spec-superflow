import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { cpSync, copyFileSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { basename, dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

assert.ok(process.argv[2], 'Pass unchanged generated modules directory');
const input = resolve(process.argv[2]);
const here = dirname(fileURLToPath(import.meta.url));
const sdk = '/Applications/DevEco-Studio.app/Contents';
const seed = process.env.KOTLIN_ETS_SDK_SEED ?? '/private/tmp/kotlin-ets-native-20260914-06/harmony';
const work = mkdtempSync('/private/tmp/kotlin-ets-scheme-modules-sdk-');
const host = join(work, 'harmony');
const hash = path => createHash('sha256').update(readFileSync(path)).digest('hex');
const modules = readdirSync(input).filter(name => name.endsWith('.ets')).map(name => ({ name, sha256: hash(join(input, name)) }));
const result = { input, work, modules, passed: false, commands: [] };
const record = () => writeFileSync(join(work, 'result.json'), JSON.stringify(result, null, 2));
console.log('SDK evidence: ' + work);
record();
const excluded = new Set(['build', '.hvigor', 'oh_modules', '.idea', '.migration', '.git']);
cpSync(seed, host, { recursive: true, filter: path => !excluded.has(basename(path)) });
const ets = join(host, 'entry/src/main/ets');
rmSync(ets, { recursive: true, force: true });
for (const name of ['pages', 'entryability', 'modules']) mkdirSync(join(ets, name), { recursive: true });
for (const module of modules) copyFileSync(join(input, module.name), join(ets, 'modules', module.name));
copyFileSync(join(here, '../../language/SdkEntryAbility.ets'), join(ets, 'entryability/EntryAbility.ets'));
// Test host only: pass a generated factory result directly to another generated module.
writeFileSync(join(ets, 'pages/Index.ets'), `import { scheme } from '../modules/Models';
import { primaryOf } from '../modules/Consumer';
@Entry
@Component
struct Index {
  build() { Text(primaryOf(scheme(false)).toString()) }
}
`);
writeFileSync(join(host, 'entry/src/main/resources/base/profile/main_pages.json'), JSON.stringify({ src: ['pages/Index'] }));
const env = { ...process.env, JAVA_HOME: join(sdk, 'jbr/Contents/Home'), DEVECO_SDK_HOME: join(sdk, 'sdk'),
  JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC',
  PATH: `${sdk}/tools/node/bin:${sdk}/tools/ohpm/bin:${process.env.PATH}` };
for (const [label, command, args] of [
  ['ohpm', 'tools/ohpm/bin/ohpm', ['install']],
  ['sdk', 'tools/hvigor/bin/hvigorw', ['assembleHap', '--mode', 'module', '-p', 'module=entry@default', '-p', 'product=default', '--no-daemon']]
]) {
  const run = spawnSync(join(sdk, command), args, { cwd: host, env, encoding: 'utf8', timeout: 300000, maxBuffer: 16 * 1024 * 1024 });
  writeFileSync(join(work, label + '.stdout'), run.stdout ?? '');
  writeFileSync(join(work, label + '.stderr'), run.stderr ?? '');
  result.commands.push({ label, status: run.status }); record();
  assert.equal(run.status, 0, run.stdout + run.stderr);
}
for (const module of modules) {
  assert.equal(hash(join(input, module.name)), module.sha256);
  assert.equal(hash(join(ets, 'modules', module.name)), module.sha256);
}
const files = readFileSync(join(host, 'entry/build/default/cache/default/default@CompileArkTS/esmodule/debug/filesInfo.txt'), 'utf8');
for (const module of modules) assert.ok(files.includes('/modules/' + module.name.replace(/\.ets$/, '.ts;')), module.name);
result.passed = true; record();
console.log('PASS unchanged generated factory, value type and consumer through actual SDK module boundary');
