import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { cpSync, copyFileSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { basename, dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../..');
assert.ok([7, 10, 13, 16, 19, 22].includes(process.argv.length), 'Pass UI evidence, binary-backed.ets, iterator modules, language Iteration.ets, stdlib Iteration.ets; optionally inheritance ETS, quantifier modules and R1 binary replay directory; then R2 generic heritage ETS, generic stdlib modules and generic binary replay directory; then bounded receiver ETS, bounded stdlib modules and extension binary replay directory; then generic methods ETS, generic-method stdlib modules and default binary replay directory; then overload ETS, overload stdlib modules and overload binary replay directory');
const [ui, binary, iteration, languageLoop, libraryLoop, inheritance, quantifiers, binaryReplay,
  genericHeritage, genericLibrary, genericBinary, boundedReceivers, boundedLibrary, extensionBinary,
  genericMethods, methodLibrary, defaultBinary, overloads, overloadLibrary, overloadBinary] = process.argv.slice(2).map(path => resolve(path));
const uiResult = JSON.parse(readFileSync(join(ui, 'result.json'), 'utf8'));
assert.equal(uiResult.passed, true, 'UI regression must complete before SDK integration');
const sdk = '/Applications/DevEco-Studio.app/Contents';
const seed = process.env.KOTLIN_ETS_SDK_SEED ?? '/private/tmp/kotlin-ets-native-20260913-07/harmony';
const work = mkdtempSync('/private/tmp/kotlin-ets-integration-sdk-');
const host = join(work, 'harmony');
const hash = path => createHash('sha256').update(readFileSync(path)).digest('hex');
const inputs = readdirSync(ui).filter(name => name.endsWith('.ets')).map(name => ({
  path: join(ui, name), destination: 'pages/' + name,
}));
assert.ok(inputs.some(input => input.destination === 'pages/fixture.ets'));
for (const file of uiResult.moduleOutputs ?? []) {
  assert.equal(hash(file.path), file.sha256, 'UI module changed after generation');
  inputs.push({ path: file.path, destination: 'pages/modules/' + (file.relativePath ?? basename(file.path)), entry: file.entry });
}
inputs.push({ path: binary, destination: 'generated/Binary.ets' });
inputs.push({ path: languageLoop, destination: 'generated/LanguageIteration.ets' });
inputs.push({ path: libraryLoop, destination: 'generated/LibraryIteration.ets' });
for (const name of ['IteratorProducer', 'IteratorConsumer', 'IteratorBridge']) {
  inputs.push({ path: join(iteration, name + '.ets'), destination: 'generated/' + name + '.ets' });
}
if (inheritance) {
  inputs.push({ path: inheritance, destination: 'generated/Inheritance.ets' });
  for (const name of ['QuantifierLibrary', 'QuantifierCases', 'NullEquality']) {
    inputs.push({ path: join(quantifiers, name + '.ets'), destination: 'generated/' + name + '.ets' });
  }
  for (const name of ['same', 'cross-facade', 'second-jar']) {
    inputs.push({ path: join(binaryReplay, name + '.ets'), destination: 'generated/' + name + '.ets' });
  }
  inputs.push({ path: join(here, 'R1Dependencies.ets'), destination: 'pages/R1Dependencies.ets', generated: false });
}
if (genericHeritage) {
  inputs.push({ path: genericHeritage, destination: 'generated/r2/GenericHeritage.ets' });
  for (const name of ['GenericModels', 'GenericCollections', 'GenericConsumers', 'GenericCases']) {
    inputs.push({ path: join(genericLibrary, name + '.ets'), destination: 'generated/r2/' + name + '.ets' });
  }
  for (const name of ['combined', 'second-jar']) {
    inputs.push({ path: join(genericBinary, name + '.ets'), destination: 'generated/r2/' + name + '.ets' });
  }
  inputs.push({ path: join(here, 'R2Dependencies.ets'), destination: 'pages/R2Dependencies.ets', generated: false });
}
if (boundedReceivers) {
  inputs.push({ path: boundedReceivers, destination: 'generated/r2b/BoundedReceivers.ets' });
  for (const name of ['BoundedModels', 'BoundedCollections', 'BoundedIterators', 'BoundedCases']) {
    inputs.push({ path: join(boundedLibrary, name + '.ets'), destination: 'generated/r2b/' + name + '.ets' });
  }
  for (const name of ['combined', 'second-jar']) {
    inputs.push({ path: join(extensionBinary, name + '.ets'), destination: 'generated/r2b/' + name + '.ets' });
  }
  inputs.push({ path: join(here, 'R2BoundedDependencies.ets'), destination: 'pages/R2BoundedDependencies.ets', generated: false });
}
if (genericMethods) {
  inputs.push({ path: genericMethods, destination: 'generated/r2c/GenericMethods.ets' });
  for (const name of ['MethodContracts', 'MethodProjectors', 'MethodPipeline', 'MethodConsumers', 'MethodCases']) {
    inputs.push({ path: join(methodLibrary, name + '.ets'), destination: 'generated/r2c/' + name + '.ets' });
  }
  for (const name of ['combined', 'second-jar']) {
    inputs.push({ path: join(defaultBinary, name + '.ets'), destination: 'generated/r2c/' + name + '.ets' });
  }
  inputs.push({ path: join(root, 'tests/stdlib/generic-methods/SdkConsumer.ets'), destination: 'generated/r2c/SdkConsumer.ets', generated: false });
  inputs.push({ path: join(here, 'R2MethodDependencies.ets'), destination: 'pages/R2MethodDependencies.ets', generated: false });
}
if (overloads) {
  inputs.push({ path: overloads, destination: 'generated/r2d/Overloads.ets' });
  for (const name of ['OverloadChoices', 'OverloadSelector', 'OverloadPipeline', 'OverloadConsumer', 'OverloadCases']) {
    inputs.push({ path: join(overloadLibrary, name + '.ets'), destination: 'generated/r2d/' + name + '.ets' });
  }
  for (const name of ['combined', 'split', 'reversed']) {
    inputs.push({ path: join(overloadBinary, name + '.ets'), destination: 'generated/r2d/' + name + '.ets' });
  }
  inputs.push({ path: join(root, 'tests/stdlib/overloads/SdkConsumer.ets'), destination: 'generated/r2d/SdkConsumer.ets', generated: false });
  inputs.push({ path: join(here, 'R2OverloadDependencies.ets'), destination: 'pages/R2OverloadDependencies.ets', generated: false });
}
for (const input of inputs) input.sha256 = hash(input.path);
function identities(directory) {
  return readdirSync(directory, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name)).flatMap(entry => {
    const path = join(directory, entry.name);
    return entry.isDirectory() ? identities(path) : [{ path, sha256: hash(path) }];
  });
}
const manifest = { seed, host, inputs, implementation: identities(join(root, 'src')), commands: [], passed: false };
for (const file of uiResult.implementation) assert.equal(hash(file.path), file.sha256, 'UI output belongs to a different compiler revision');
for (const file of uiResult.sourceInputs) assert.equal(hash(file.path), file.sha256, 'UI input changed after generation');
for (const file of uiResult.outputs) assert.equal(hash(file.path), file.sha256, 'UI output changed after regression');
const record = () => writeFileSync(join(work, 'manifest.json'), JSON.stringify(manifest, null, 2) + '\n');
const env = { ...process.env, JAVA_HOME: join(sdk, 'jbr/Contents/Home'), DEVECO_SDK_HOME: join(sdk, 'sdk'),
  PATH: `${sdk}/tools/node/bin:${sdk}/tools/ohpm/bin:${process.env.PATH}` };
function run(label, command, args) {
  const result = spawnSync(command, args, { cwd: host, env, encoding: 'utf8', timeout: 600000, maxBuffer: 32 * 1024 * 1024 });
  writeFileSync(join(work, label + '.stdout'), result.stdout ?? '');
  writeFileSync(join(work, label + '.stderr'), result.stderr ?? '');
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
for (const name of ['pages', 'generated', 'entryability']) mkdirSync(join(ets, name), { recursive: true });
for (const input of inputs) {
  mkdirSync(dirname(join(ets, input.destination)), { recursive: true });
  copyFileSync(input.path, join(ets, input.destination));
}
copyFileSync(join(root, 'tests/language/SdkEntryAbility.ets'), join(ets, 'entryability/EntryAbility.ets'));
// Keep the ability's standard entry route without changing the generated page.
copyFileSync(join(here, 'Dependencies.ets'), join(ets, 'pages/Index.ets'));
const routes = ['pages/Index', ...inputs.filter(input => input.destination.startsWith('pages/') && input.entry !== false)
  .map(input => input.destination.slice(0, -4))];
writeFileSync(join(host, 'entry/src/main/resources/base/profile/main_pages.json'), JSON.stringify({ src: routes }));
try {
  run('ohpm-install', join(sdk, 'tools/ohpm/bin/ohpm'), ['install']);
  run('sdk-assemble', join(sdk, 'tools/hvigor/bin/hvigorw'),
    ['assembleHap', '--mode', 'module', '-p', 'module=entry@default', '-p', 'product=default', '--no-daemon']);
  const filesInfo = join(host, 'entry/build/default/cache/default/default@CompileArkTS/esmodule/debug/filesInfo.txt');
  const records = readFileSync(filesInfo, 'utf8').split('\n');
  manifest.compiledModules = inputs.map(input => {
    const item = records.find(line => line.includes('/' + input.destination.slice(0, -4) + '.ts;') && line.endsWith(';ets'));
    assert.ok(item, 'Missing SDK input: ' + input.destination);
    return item;
  });
  const abc = join(host, 'entry/build/default/intermediates/loader_out/default/ets/modules.abc');
  manifest.abc = { path: abc, sha256: hash(abc) };
  const outputs = join(host, 'entry/build/default/outputs/default');
  manifest.haps = readdirSync(outputs).filter(name => name.endsWith('.hap')).map(name => ({ path: join(outputs, name), sha256: hash(join(outputs, name)) }));
  assert.ok(manifest.haps.length > 0);
  manifest.passed = true;
} finally {
  for (const input of inputs) {
    assert.equal(hash(input.path), input.sha256, 'Generated original changed');
    assert.equal(hash(join(ets, input.destination)), input.sha256, 'SDK generated copy changed');
  }
  assert.deepEqual(identities(join(root, 'src')), manifest.implementation, 'Compiler changed during SDK verification');
  manifest.generatedBytesUnchanged = true;
  record();
}
console.log(`PASS actual ETS SDK: ${inputs.filter(input => input.generated !== false).length} unchanged generated modules, explicit test consumers and HAP output`);
