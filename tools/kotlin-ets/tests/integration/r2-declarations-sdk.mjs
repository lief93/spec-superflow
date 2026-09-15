import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { copyFileSync, cpSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { basename, dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';
import { verifyModuleCoverage } from '../modules/ui-sdk-evidence.mjs';

const here = dirname(fileURLToPath(import.meta.url)), root = resolve(here, '../..');
assert.ok([7, 9].includes(process.argv.length), 'Pass defaults, constructors, bridges, variance and binary replay evidence; optionally --device <HDC key>');
if (process.argv.length === 9) assert.equal(process.argv[7], '--device');
const device = process.argv[8];
const hash = path => createHash('sha256').update(readFileSync(path)).digest('hex');
const read = path => JSON.parse(readFileSync(path, 'utf8'));
const groups = ['defaults', 'constructors', 'bridges', 'variance', 'binary'];
const counts = [65, 90, 70, 160, 3];
const reports = process.argv.slice(2, 7).map((path, i) => ({ name: groups[i], path: resolve(path), result: read(join(path, 'result.json')) }));
const inputs = new Map();
function pin(input) {
  assert.equal(hash(input.path), input.sha256, `Changed evidence input: ${input.path}`);
  if (inputs.has(input.path)) assert.equal(inputs.get(input.path).sha256, input.sha256);
  inputs.set(input.path, input);
}
const implementation = readdirSync(join(root, 'src'), { recursive: true }).filter(p => p.endsWith('.kt')).sort()
  .map(p => ({ path: join(root, 'src', p), sha256: hash(join(root, 'src', p)) }));
for (const [i, report] of reports.entries()) {
  const r = report.result;
  assert.equal(r.passed, true, report.name);
  assert.equal(r.expected.length, counts[i]);
  assert.deepEqual(r.actual, r.expected);
  if (report.name !== 'binary') assert.deepEqual(r.moduleActual, r.expected);
  const recorded = r.inputs ?? r.implementation;
  for (const source of implementation) assert.equal(recorded.find(f => f.path === source.path)?.sha256, source.sha256, report.name + ': ' + source.path);
  [...recorded, ...(r.producerInputs ?? [])].forEach(pin);
  pin({ path: join(report.path, 'result.json'), sha256: hash(join(report.path, 'result.json')) });
}
const sdk = '/Applications/DevEco-Studio.app/Contents';
const seed = process.env.KOTLIN_ETS_SDK_SEED ?? '/private/tmp/kotlin-ets-native-20260913-07/harmony';
const work = mkdtempSync('/private/tmp/kotlin-ets-r2-declarations-'), host = join(work, 'harmony');
const modules = [], expected = reports.flatMap(r => r.result.expected);
const result = { level: 'Joint existing declaration and member-inline corpus; not whole R2 or UI acceptance',
  reports: reports.map(({ name, path }, i) => ({ name, path, cases: counts[i] })), inputs: [], modules, commands: [],
  expected, sdkPassed: false, nativePassed: false };
const record = () => writeFileSync(join(work, 'result.json'), JSON.stringify(result, null, 2));
const hostEnv = { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' };
const sdkEnv = { ...hostEnv, JAVA_HOME: join(sdk, 'jbr/Contents/Home'), DEVECO_SDK_HOME: join(sdk, 'sdk'),
  PATH: `${sdk}/tools/node/bin:${sdk}/tools/ohpm/bin:${process.env.PATH}` };
function run(label, command, args, cwd = root, env = hostEnv) {
  const r = spawnSync(command, args, { cwd, env, encoding: 'utf8', timeout: 600000, maxBuffer: 32 * 1024 * 1024 });
  writeFileSync(join(work, label + '.stdout'), r.stdout ?? ''); writeFileSync(join(work, label + '.stderr'), r.stderr ?? '');
  result.commands.push({ label, command, args, status: r.status, error: r.error?.message }); record();
  assert.equal(r.error, undefined); assert.equal(r.status, 0, r.stdout + r.stderr); return r.stdout;
}
console.log(`Evidence: ${work}`);
record();
for (const report of reports) {
  const r = report.result;
  let files;
  if (report.name === 'binary') {
    files = [{ name: 'Application.ets', path: r.output, sha256: r.sha256 },
      { name: 'Receivers.ets', path: join(root, 'tests/binary-bodies/r2e/Receivers.ets'),
        sha256: hash(join(root, 'tests/binary-bodies/r2e/Receivers.ets')), replacement: true }];
  } else if (r.modules) {
    files = r.modules;
  } else {
    // The older default suite has no per-module hashes. Regenerate from its
    // pinned public CLI command and compare both recorded input orders.
    const command = r.commands.find(c => c.label === 'modules');
    assert.equal(command.status, 0);
    const args = [...command.args], outputIndex = args.indexOf('--out-dir') + 1;
    assert.ok(outputIndex > 0);
    const destination = join(work, 'defaults'); args[outputIndex] = destination;
    run('regenerate-defaults', command.command, args);
    const names = readdirSync(destination).sort();
    assert.deepEqual(names, ['Application.ets', 'Captures.ets', 'Ownership.ets', 'Provider.ets', 'Sibling.ets']);
    files = names.map(name => {
      const path = join(destination, name), sha256 = hash(path);
      for (const dir of ['modules', 'reversed']) assert.equal(hash(join(report.path, dir, name)), sha256);
      return { name, path, sha256 };
    });
  }
  for (const file of files) { pin(file); modules.push({ ...file, name: report.name + '/' + file.name }); }
}

// These are test-host calls to existing generated exports, not translated bodies.
const imports = new Map(), declarations = new Map();
function symbol(group, name) {
  const matches = modules.filter(m => m.name.startsWith(group + '/')).filter(m => {
    const tree = ts.createSourceFile(m.name, readFileSync(m.path, 'utf8'), ts.ScriptTarget.Latest, true);
    assert.equal(tree.parseDiagnostics.length, 0);
    const declaration = tree.statements.find(n => (ts.isFunctionDeclaration(n) || ts.isClassDeclaration(n)) && n.name?.text === name &&
      n.modifiers?.some(modifier => modifier.kind === ts.SyntaxKind.ExportKeyword));
    if (declaration) declarations.set(group + '_' + name, declaration);
    return declaration !== undefined;
  });
  assert.equal(matches.length, 1, group + '.' + name);
  const alias = group + '_' + name;
  imports.set(alias, `import { ${name} as ${alias} } from '../modules/${matches[0].name.slice(0, -4)}';`);
  return alias;
}
const cases = {
  defaults: ['defaults', 'genericDefaults', 'closureDefaults', 'recursiveDefaults', 'nullableDefaults', 'bitwiseDefaults', 'wideDefaults',
    'heritageDefaults', 'namedEffects', 'ownedDefaults', 'siblingDefaults', 'localCapturedDefaults', 'innerCapturedDefaults'],
  constructors: ['construct', 'generic', 'inherited', 'captured', 'defaults', 'privateChain', 'reference', 'nativeRoot', 'genericRoot',
    'inheritedRoot', 'privateRoot', 'dispatchRoots', 'dispatchInheritance', 'dispatchGeneric', 'dispatchDefaults', 'dispatchEarly', 'protectedConstruction'],
  bridges: ['bridgeJoin', 'inheritedBridge', 'bridgeEffects', 'voidBridge', 'genericBridge', 'nullableBridge', 'fakeBridge', 'inheritedComposition',
    'bareBridge', 'covariantDispatch', 'covariantBounds', 'covariantNullable', 'covariantJoined', 'covariantProperties'],
  variance: ['covariance', 'contravariance', 'nested', 'property', 'mixed', 'nullable', 'broadBound', 'narrowBound', 'classBound', 'nominalBound',
    'independent', 'independentGeneric', 'independentClass', 'independentSelf', 'independentChain', 'independentDiamond', 'originalMultiple',
    'classInterface', 'interfaceClass', 'classInterfaceReturn', 'classInterfaceHolder', 'classInterfaceMutation', 'projectedRead', 'projectedWrite',
    'projectedStar', 'projectedBound', 'projectedNested', 'projectedGeneric', 'projectedVisit', 'projectedReplace', 'projectedLater'],
};
const body = ['const values: string[] = [];'];
for (const [group, names] of Object.entries(cases)) {
  body.push('for (const seed of [0, -3, 7, -2147483648, 2147483647]) {');
  for (const name of names) {
    const alias = symbol(group, name), declaration = declarations.get(alias);
    assert.ok(ts.isFunctionDeclaration(declaration));
    assert.ok(declaration.parameters.length <= 1, 'Unexpected corpus signature: ' + alias);
    body.push(`values.push(String(${alias}(${declaration.parameters.length ? 'seed' : ''})));`);
  }
  if (group === 'constructors') body.push(`const trace = new ${symbol(group, 'Trace')}();`, "let outcome = 'ok';",
    `try { ${symbol(group, 'failure')}(trace, seed); } catch (error) {`,
    "if (!(error instanceof Error) || !error.message.toLowerCase().includes('zero')) { throw new Error('Unexpected constructor failure'); } outcome = 'error'; }",
    "values.push(outcome + ':' + trace.value);");
  if (group === 'variance') body.push(`const cell = new ${symbol(group, 'Cell')}<${symbol(group, 'Specific')}>(new ${symbol(group, 'Specific')}(seed));`,
    `values.push(String(${symbol(group, 'project')}(cell) === cell));`);
  body.push('}');
}
body.push('for (const seed of [1, -2, 2147483647]) {',
  `values.push(${symbol('binary', 'scenario')}(new ${symbol('binary', 'FinalMember')}(), new ${symbol('binary', 'PeerMember')}(), seed));`,
  '}', 'return values;');
const consumer = join(work, 'Index.ets');
writeFileSync(consumer, [...imports.values(), '', 'function runCorpus(): string[] {', ...body.map(l => '  ' + l), '}', '',
  '@Entry', '@Component', 'struct Index {', '  build() {', "    Text(JSON.stringify(runCorpus())).id('r2-native-results').maxLines(2)", '  }', '}', ''].join('\n'));
const ability = join(root, 'tests/language/SdkEntryAbility.ets');
for (const path of [consumer, ability, fileURLToPath(import.meta.url), join(here, '../modules/ui-sdk-evidence.mjs')]) pin({ path, sha256: hash(path) });
result.inputs = [...inputs.values()]; record();
const excluded = new Set(['build', '.hvigor', 'oh_modules', '.idea', '.migration', '.git']);
cpSync(seed, host, { recursive: true, filter: path => !excluded.has(basename(path)) });
const ets = join(host, 'entry/src/main/ets'); rmSync(ets, { recursive: true, force: true });
for (const path of ['pages', 'entryability', 'modules']) mkdirSync(join(ets, path), { recursive: true });
copyFileSync(consumer, join(ets, 'pages/Index.ets')); copyFileSync(ability, join(ets, 'entryability/EntryAbility.ets'));
writeFileSync(join(host, 'entry/src/main/resources/base/profile/main_pages.json'), JSON.stringify({ src: ['pages/Index'] }));
for (const file of modules) { mkdirSync(dirname(join(ets, 'modules', file.name)), { recursive: true }); copyFileSync(file.path, join(ets, 'modules', file.name)); }
run('ohpm', join(sdk, 'tools/ohpm/bin/ohpm'), ['install'], host, sdkEnv);
run('sdk', join(sdk, 'tools/hvigor/bin/hvigorw'), ['assembleHap', '--mode', 'module', '-p', 'module=entry@default', '-p', 'product=default', '--no-daemon'], host, sdkEnv);
const cache = join(host, 'entry/build/default/cache/default/default@CompileArkTS/esmodule');
const buildInfoPath = join(cache, '.tsbuildinfo');
result.coverage = verifyModuleCoverage({ modules, ets, records: readFileSync(join(cache, 'debug/filesInfo.txt'), 'utf8').split('\n'),
  buildInfoPath, buildInfo: read(buildInfoPath), checker: read(join(cache, '.ts_checker_cache')) });
result.abc = { path: join(host, 'entry/build/default/intermediates/loader_out/default/ets/modules.abc') }; result.abc.sha256 = hash(result.abc.path);
result.hap = { path: join(host, 'entry/build/default/outputs/default/entry-default-signed.hap') }; result.hap.sha256 = hash(result.hap.path);
result.sdkPassed = true; record();
if (device) {
  const hdc = join(sdk, 'sdk/default/openharmony/toolchains/hdc');
  const targets = run('targets', hdc, ['list', 'targets']).trim().split(/\s+/); assert.ok(targets.includes(device));
  assert.match(run('install', hdc, ['-t', device, 'install', '-r', result.hap.path]), /install bundle successfully/);
  assert.match(run('launch', hdc, ['-t', device, 'shell', 'aa', 'start', '-a', 'EntryAbility', '-b', 'com.joker.kit']), /start ability successfully/);
  // Retry only observation while the newly launched ability creates its window.
  for (let attempt = 0; attempt < 10; attempt++) {
    const output = run('dump-' + attempt, hdc, ['-t', device, 'shell', 'uitest', 'dumpLayout', '-b', 'com.joker.kit']);
    const remote = /DumpLayout saved to:(\S+)/.exec(output)?.[1]; assert.ok(remote, output);
    const path = join(work, `layout-${attempt}.json`); run('receive-' + attempt, hdc, ['-t', device, 'file', 'recv', remote, path]);
    const flatten = n => [n, ...(n.children ?? []).flatMap(flatten)];
    const window = flatten(read(path)).find(n => n.attributes.bundleName === 'com.joker.kit' && n.attributes.pagePath === 'pages/Index');
    const node = window && flatten(window).find(n => n.attributes.id === 'r2-native-results');
    if (!node) { await new Promise(r => setTimeout(r, 1000)); continue; }
    result.actual = JSON.parse(node.attributes.text); result.layout = { path, sha256: hash(path) }; record();
    assert.deepEqual(result.actual, expected); result.nativePassed = true; break;
  }
  assert.equal(result.nativePassed, true, 'No matching native result node');
}
for (const input of inputs.values()) pin(input);
for (const file of modules) assert.equal(hash(join(ets, 'modules', file.name)), file.sha256);
result.passed = true; record();
console.log(`PASS ${modules.length} unchanged modules in one SDK build; ${device ? expected.length + ' JVM/native outcomes' : 'native not run'}; not whole R2`);
