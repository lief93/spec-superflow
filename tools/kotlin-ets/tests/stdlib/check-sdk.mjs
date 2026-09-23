import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { cpSync, existsSync, mkdirSync, mkdtempSync, openSync, closeSync, readFileSync,
  readdirSync, lstatSync, readlinkSync, rmSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { assertRuntimeHelpers } from './runtime-assertions.mjs';

const tests = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(tests, '../..');
const seed = path.resolve(process.argv[2] ?? '/private/tmp/kotlin-ets-native-20260913-07/harmony');
assert.ok(existsSync(path.join(seed, 'build-profile.json5')), 'Harmony SDK host seed is missing');
const run = mkdtempSync('/tmp/kotlin-ets-stdlib-sdk-');
const host = path.join(run, 'harmony');
const deveco = '/Applications/DevEco-Studio.app/Contents';
const overrides = {
  JAVA_HOME: `${deveco}/jbr/Contents/Home`,
  DEVECO_SDK_HOME: `${deveco}/sdk`,
  PATH: `${deveco}/tools/node/bin:${deveco}/tools/ohpm/bin:${process.env.PATH}`,
};
const ignored = new Set(['build', '.hvigor', '.idea', '.migration']);
const hash = file => createHash('sha256').update(readFileSync(file)).digest('hex');
const write = (file, value) => writeFileSync(file, JSON.stringify(value, null, 2) + '\n');
function seedFiles(directory, prefix = '') {
  return readdirSync(directory).sort().flatMap(name => {
    if (ignored.has(name)) return [];
    const relative = path.join(prefix, name);
    const full = path.join(directory, name);
    const stat = lstatSync(full);
    if (stat.isSymbolicLink()) return [{ path: relative, symlink: readlinkSync(full) }];
    if (stat.isDirectory()) return seedFiles(full, relative);
    return [{ path: relative, sha256: hash(full) }];
  });
}
const openingSeed = seedFiles(seed);
const commands = [];
const inputs = [];
let artifacts = [];
console.log(`SDK evidence directory: ${run}`);
write(path.join(run, 'seed-inputs.json'), { seed, files: openingSeed });
function execute(name, argv, cwd) {
  const stdout = path.join(run, `${name}.stdout`);
  const stderr = path.join(run, `${name}.stderr`);
  const out = openSync(stdout, 'w');
  const err = openSync(stderr, 'w');
  const command = { name, argv, cwd, overrides, stdout, stderr, started: new Date().toISOString() };
  commands.push(command);
  write(path.join(run, 'commands.json'), commands);
  const result = spawnSync(argv[0], argv.slice(1), {
    cwd, env: { ...process.env, ...overrides }, stdio: ['ignore', out, err], timeout: 600000,
  });
  closeSync(out);
  closeSync(err);
  Object.assign(command, { exit: result.status, signal: result.signal,
    error: result.error?.message, finished: new Date().toISOString() });
  write(path.join(run, 'commands.json'), commands);
  assert.equal(result.status, 0, `${name} failed; see ${stdout} and ${stderr}`);
}
try {
  cpSync(seed, host, { recursive: true, verbatimSymlinks: true,
    filter: source => !ignored.has(path.basename(source)) });
  // Replace only the cloned host's page. Generated module bytes are copied verbatim.
  const pages = path.join(host, 'entry/src/main/ets/pages');
  rmSync(pages, { recursive: true });
  mkdirSync(pages);
  cpSync(path.join(tests, 'sdk/Index.ets'), path.join(pages, 'Index.ets'));
  const generated = path.join(host, 'entry/src/main/ets/generated');
  mkdirSync(generated);
  for (const fixture of ['Scalars', 'Lists']) {
    const source = path.join(tests, 'fixtures', `${fixture}.kt`);
    const output = path.join(run, `${fixture}.ets`);
    const copy = path.join(generated, `${fixture}.ets`);
    const sourceHash = hash(source);
    execute(`generate-${fixture}`, [path.join(root, 'kotlin-ets'), '--mode', 'language', '--out', output, source], root);
    assertRuntimeHelpers(output, fixture === 'Scalars'
      ? ['__etsIntDiv', '__etsIntRem', '__etsListAdd', '__etsSubstring', '__etsSubstringFrom']
      : ['__etsListGet', '__etsListContains', '__etsListAdd', '__etsListMap']);
    cpSync(output, copy);
    inputs.push({ source, sourceHash, output, copy, sha256: hash(output) });
    write(path.join(run, 'generated-inputs.json'), inputs);
  }
  execute('sdk-assemble', [`${deveco}/tools/hvigor/bin/hvigorw`, 'assembleHap', '--mode', 'module',
    '-p', 'module=entry@default', '-p', 'product=default', '--no-daemon'], host);
  const compilerCache = path.join(host, 'entry/build/default/cache/default/default@CompileArkTS/esmodule/debug');
  const fileInfo = path.join(compilerCache, 'filesInfo.txt');
  const compilerInputs = readFileSync(fileInfo, 'utf8').trim().split('\n').map(line => line.split(';'));
  const compiledModules = ['Scalars', 'Lists'].map(name => {
    assert.ok(compilerInputs.some(row => row[0].endsWith(`/src/main/ets/generated/${name}.ts`) &&
      row[2] === 'esm' && row[6] === 'ets'), `${name} missing from SDK ETS compilation inputs`);
    const binary = path.join(compilerCache, 'entry/src/main/ets/generated', `${name}.protoBin`);
    assert.ok(lstatSync(binary).size > 0, `${name} has no compiled module`);
    return binary;
  });
  const bytecode = path.join(host, 'entry/build/default/intermediates/loader_out/default/ets/modules.abc');
  assert.ok(lstatSync(bytecode).size > 0, 'SDK produced no Ark bytecode');
  const outputs = path.join(host, 'entry/build/default/outputs/default');
  const haps = readdirSync(outputs).filter(name => name.endsWith('.hap')).map(name => path.join(outputs, name));
  assert.ok(haps.length > 0, 'SDK produced no HAP');
  artifacts = [...haps, bytecode, fileInfo, ...compiledModules].map(file => ({ file, sha256: hash(file) }));
} catch (error) {
  write(path.join(run, 'result.json'), { passed: false, error: error.message });
  throw error;
} finally {
  try {
    assert.deepEqual(seedFiles(seed), openingSeed, 'Read-only seed changed');
    for (const input of inputs) {
      assert.equal(hash(input.source), input.sourceHash, 'Kotlin fixture changed');
      assert.equal(hash(input.output), input.sha256, 'Generated original changed');
      assert.equal(hash(input.copy), input.sha256, 'Staged generated module changed');
    }
    write(path.join(run, 'integrity.json'), { seedUnchanged: true, generatedBytesUnchanged: true });
  } catch (error) {
    write(path.join(run, 'result.json'), { passed: false, error: error.message });
    throw error;
  }
}
write(path.join(run, 'result.json'), { passed: true, artifacts });
console.log('PASS: actual Harmony SDK assembled HAP with both generated stdlib modules imported');
