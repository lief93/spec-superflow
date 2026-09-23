import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { copyFileSync, cpSync, existsSync, lstatSync, mkdirSync, mkdtempSync,
  readFileSync, readdirSync, readlinkSync, rmSync, writeFileSync } from 'node:fs';
import { basename, dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const here = dirname(fileURLToPath(import.meta.url));
assert.ok(process.argv[2], 'Pass the positive project-input evidence directory');
const generated = resolve(process.argv[2]);
const seed = process.env.KOTLIN_ETS_SDK_SEED ?? '/private/tmp/kotlin-ets-native-20260913-07/harmony';
const deveco = '/Applications/DevEco-Studio.app/Contents';
assert.ok(existsSync(join(seed, 'build-profile.json5')), 'Harmony SDK host seed is missing');
const names = ['Values', 'Page', 'ProjectInputsHost'];
for (const name of names) assert.ok(existsSync(join(generated, `${name}.ets`)), `Missing ${name}.ets`);
const work = mkdtempSync('/private/tmp/kotlin-ets-project-input-sdk-');
const host = join(work, 'harmony');
const ignored = new Set(['build', '.hvigor', 'oh_modules', '.idea', '.migration', '.git']);
const hash = file => createHash('sha256').update(readFileSync(file)).digest('hex');
const write = (name, value) => writeFileSync(join(work, name), JSON.stringify(value, null, 2) + '\n');
function snapshot(directory, prefix = '') {
  return readdirSync(directory).sort().flatMap(name => {
    if (ignored.has(name)) return [];
    const relative = join(prefix, name), full = join(directory, name), stat = lstatSync(full);
    if (stat.isSymbolicLink()) return [{ path: relative, symlink: readlinkSync(full) }];
    return stat.isDirectory() ? snapshot(full, relative) : [{ path: relative, sha256: hash(full) }];
  });
}
const openingSeed = snapshot(seed);
const commands = [];
const inputs = [];
const env = { ...process.env, JAVA_HOME: join(deveco, 'jbr/Contents/Home'),
  DEVECO_SDK_HOME: join(deveco, 'sdk'),
  PATH: `${deveco}/tools/node/bin:${deveco}/tools/ohpm/bin:${process.env.PATH}` };
function run(name, command, args, cwd) {
  const result = spawnSync(command, args, { cwd, env, encoding: 'utf8', timeout: 600000,
    maxBuffer: 32 * 1024 * 1024 });
  commands.push({ name, command, args, cwd, status: result.status, signal: result.signal,
    error: result.error?.message, stdout: result.stdout, stderr: result.stderr });
  write('commands.json', commands);
  assert.equal(result.status, 0, `${name}: ${result.stdout}\n${result.stderr}`);
}
console.log(`SDK evidence: ${work}`);
try {
  cpSync(seed, host, { recursive: true, verbatimSymlinks: true,
    filter: source => !ignored.has(basename(source)) });
  const ets = join(host, 'entry/src/main/ets');
  rmSync(join(ets, 'pages'), { recursive: true, force: true });
  mkdirSync(join(ets, 'pages'), { recursive: true });
  writeFileSync(join(host, 'entry/src/main/resources/base/profile/main_pages.json'),
    JSON.stringify({ src: ['pages/SdkIndex'] }) + '\n');
  copyFileSync(join(here, 'SdkIndex.ets'), join(ets, 'pages/SdkIndex.ets'));
  const media = join(host, 'entry/src/main/resources/base/media');
  mkdirSync(media, { recursive: true });
  writeFileSync(join(media, 'project_input.svg'),
    '<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8"><rect width="8" height="8" fill="#336699"/></svg>\n');
  for (const name of names) {
    const original = join(generated, `${name}.ets`), copy = join(ets, 'pages', `${name}.ets`);
    copyFileSync(original, copy);
    inputs.push({ name, original, copy, sha256: hash(original) });
  }
  write('inputs.json', { seed, generated, inputs });
  run('ohpm-install', join(deveco, 'tools/ohpm/bin/ohpm'), ['install'], host);
  run('sdk-assemble', join(deveco, 'tools/hvigor/bin/hvigorw'), ['assembleHap', '--mode', 'module',
    '-p', 'module=entry@default', '-p', 'product=default', '--no-daemon'], host);
  const cache = join(host, 'entry/build/default/cache/default/default@CompileArkTS/esmodule/debug');
  const fileInfo = join(cache, 'filesInfo.txt');
  const records = readFileSync(fileInfo, 'utf8').trim().split('\n').map(line => line.split(';'));
  const compiled = inputs.map(input => {
    const record = records.find(row => row[0].endsWith(`/src/main/ets/pages/${input.name}.ts`) &&
      row[2] === 'esm' && row[6] === 'ets');
    assert.ok(record, `${input.name}.ets omitted from SDK inputs`);
    const proto = join(cache, 'entry/src/main/ets/pages', `${input.name}.protoBin`);
    assert.ok(lstatSync(proto).size > 0, `${input.name}.protoBin is empty`);
    return { name: input.name, record, proto, sha256: hash(proto) };
  });
  const abc = join(host, 'entry/build/default/intermediates/loader_out/default/ets/modules.abc');
  assert.ok(lstatSync(abc).size > 0, 'SDK produced no Ark bytecode');
  const output = join(host, 'entry/build/default/outputs/default');
  const haps = readdirSync(output).filter(name => name.endsWith('.hap')).map(name => join(output, name));
  assert.ok(haps.length > 0, 'SDK produced no HAP');
  for (const input of inputs) {
    assert.equal(hash(input.original), input.sha256);
    assert.equal(hash(input.copy), input.sha256);
  }
  assert.deepEqual(snapshot(seed), openingSeed, 'Read-only SDK seed changed');
  write('result.json', { passed: true, seedUnchanged: true, generatedBytesUnchanged: true,
    fileInfo: { path: fileInfo, sha256: hash(fileInfo) }, compiled,
    abc: { path: abc, sha256: hash(abc) }, haps: haps.map(path => ({ path, sha256: hash(path) })) });
  console.log('PASS: DevEco SDK compiled all project input categories and structured business-component slot');
} catch (error) {
  write('result.json', { passed: false, error: error.message });
  throw error;
}
