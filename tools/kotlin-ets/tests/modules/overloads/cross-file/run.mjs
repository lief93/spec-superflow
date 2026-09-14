import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { copyFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { basename, dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';

assert.equal(process.env.KOTLIN_ETS_BUILD_SLOT, '1', 'Main must grant the exclusive isolated compiler slot');
const here = dirname(fileURLToPath(import.meta.url)), root = resolve(here, '../../../..');
const baselineIndex = process.argv.indexOf('--baseline-naming');
const baseline = baselineIndex >= 0;
const privateBaseline = process.argv.includes('--baseline-private-import');
assert.ok(!privateBaseline || baseline, '--baseline-private-import requires --baseline-naming');
const originalBaseline = baseline && !privateBaseline;
assert.ok(!baseline || process.argv[baselineIndex + 1], 'Pass the preserved pre-edit OverloadNaming.kt');
const baselineNaming = baseline ? resolve(process.argv[baselineIndex + 1]) : undefined;
const hash = path => createHash('sha256').update(readFileSync(path)).digest('hex');
const productionPaths = () => readdirSync(join(root, 'src'), { recursive: true }).filter(name => name.endsWith('.kt'))
  .map(name => join(root, 'src', name)).sort();
const live = productionPaths().map(path => ({ path, sha256: hash(path) }));
mkdirSync(join(here, '../.work'), { recursive: true });
const work = mkdtempSync(join(here, baseline ? '../.work/r2e-red-' : '../.work/r2e-green-'));
console.log(`Evidence: ${work}`);
const fixturePaths = readdirSync(here, { recursive: true }).filter(name => name.endsWith('.kt') || name === 'run.mjs')
  .map(name => join(here, name)).sort();
const inputs = [...live.map(input => input.path), ...fixturePaths, join(root, 'tests/stdlib/compiler.sh')].map(original => {
  const path = baseline && original === join(root, 'src/language/OverloadNaming.kt') ? baselineNaming : original;
  const snapshot = join(work, 'frozen', relative(root, original));
  const sha256 = hash(path);
  mkdirSync(dirname(snapshot), { recursive: true }); copyFileSync(path, snapshot);
  assert.equal(hash(snapshot), sha256);
  return { path, snapshot, sha256 };
});
const result = { phase: privateBaseline ? 'private-import-baseline' : baseline ? 'baseline' : 'current', live, inputs, commands: [], comparisons: [], passed: false };
const record = () => writeFileSync(join(work, 'result.json'), JSON.stringify(result, null, 2));
function guard() {
  assert.deepEqual(productionPaths(), live.map(input => input.path), 'Production file set changed');
  for (const input of live) assert.equal(hash(input.path), input.sha256, `Production changed: ${input.path}`);
  for (const input of inputs) {
    assert.equal(hash(input.path), input.sha256, `Input changed: ${input.path}`);
    assert.equal(hash(input.snapshot), input.sha256, `Snapshot changed: ${input.snapshot}`);
  }
}
const env = { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' };
function run(label, command, args, expectedStatus = 0) {
  guard();
  const value = spawnSync(command, args, { cwd: root, env, encoding: 'utf8', timeout: 600000, maxBuffer: 32 * 1024 * 1024 });
  writeFileSync(join(work, label + '.stdout'), value.stdout ?? '');
  writeFileSync(join(work, label + '.stderr'), value.stderr ?? '');
  result.commands.push({ label, command, args, status: value.status, error: value.error?.message }); record();
  assert.equal(value.error, undefined); assert.equal(value.status, expectedStatus, value.stdout + value.stderr);
  guard(); return value;
}
record();
const frozen = join(work, 'frozen'), fixtures = join(frozen, relative(root, here));
const compiler = join(frozen, 'tests/stdlib/compiler.sh');
const sources = ['AInt.kt', 'BDouble.kt', 'Calls.kt', 'Trace.kt'].map(name => join(fixtures, name));
const cp = run('classpath', 'bash', [compiler, '--classpath']).stdout.trim();
const oracle = join(work, 'oracle.jar');
run('oracle-build', 'bash', [compiler, ...sources, join(fixtures, 'JvmOracle.kt'), '-d', oracle]);
result.expected = run('oracle', 'java', ['-cp', `${oracle}:${cp}`, 'crossfileoverloads.JvmOracleKt']).stdout.trimEnd().split('\n');
assert.equal(result.expected.length, 15); record();
const jar = join(work, 'backend.jar');
run('backend-build', 'bash', [compiler, ...inputs.filter(input => input.snapshot.startsWith(join(frozen, 'src') + '/')).map(input => input.snapshot),
  join(fixtures, 'CrossFileProbe.kt'), '-d', jar]);
const forward = join(work, 'forward'); mkdirSync(forward);
const probe = run('forward', 'java', ['-cp', `${jar}:${cp}`, 'dev.ets.CrossFileProbeKt', cp, forward,
  originalBaseline ? 'baseline' : 'current', ...sources], originalBaseline ? 1 : 0);
if (originalBaseline) {
  assert.match(probe.stderr, /Conflicting module binding/);
  assert.ok(existsSync(join(forward, 'actual.ir')));
  assert.equal(existsSync(join(forward, 'modules')), false);
  result.expectedRejection = 'Conflicting module binding';
} else {
  const reverse = join(work, 'reverse'); mkdirSync(reverse);
  run('reverse', 'java', ['-cp', `${jar}:${cp}`, 'dev.ets.CrossFileProbeKt', cp, reverse, 'current', ...sources.toReversed()]);
  const outputs = readdirSync(join(forward, 'modules')).sort();
  assert.deepEqual(outputs, sources.map(path => basename(path).replace(/\.kt$/, '.ets')).sort());
  for (const name of [...outputs, 'Combined.ets']) {
    const path = name === 'Combined.ets' ? join(forward, name) : join(forward, 'modules', name);
    const counterpart = name === 'Combined.ets' ? join(reverse, name) : join(reverse, 'modules', name);
    // Flat output retains input-file declaration order; module bytes must not change.
    if (name !== 'Combined.ets') assert.equal(hash(path), hash(counterpart), `Input-order drift: ${name}`);
  }
  const texts = new Map(outputs.map(name => [name, readFileSync(join(forward, 'modules', name), 'utf8')]));
  function checkImports(texts) {
  const syntax = new Map([...texts].map(([name, text]) => [name, ts.createSourceFile(name, text, ts.ScriptTarget.Latest, true)]));
  for (const [name, source] of syntax) {
    assert.equal(source.parseDiagnostics.length, 0);
    for (const declaration of source.statements.filter(ts.isImportDeclaration)) {
      assert.ok(ts.isStringLiteral(declaration.moduleSpecifier));
      const destination = declaration.moduleSpecifier.text.slice(2) + '.ets';
      assert.ok(syntax.has(destination), `Unresolved module import in ${name}`);
      assert.ok(ts.isNamedImports(declaration.importClause.namedBindings));
      const exports = syntax.get(destination).statements.filter(node => ts.isFunctionDeclaration(node) || ts.isClassDeclaration(node))
        .filter(node => node.modifiers?.some(modifier => modifier.kind === ts.SyntaxKind.ExportKeyword)).map(node => node.name.text);
      for (const specifier of declaration.importClause.namedBindings.elements) {
        assert.equal(specifier.propertyName, undefined, 'No output alias pass in this increment');
        assert.ok(exports.includes(specifier.name.text), `Missing exported binding ${specifier.name.text}`);
      }
    }
  }
  }
  checkImports(texts);
  function loader(modules) {
    const cache = new Map();
    function load(name) {
      if (cache.has(name)) return cache.get(name).exports;
      assert.ok(modules.has(name), `Unknown generated module: ${name}`);
      const output = ts.transpileModule(modules.get(name), { compilerOptions: {
        target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS,
      }, reportDiagnostics: true });
      assert.deepEqual(output.diagnostics, []);
      const module = { exports: {} }; cache.set(name, module);
      vm.runInNewContext(output.outputText, { module, exports: module.exports, require(specifier) {
        assert.ok(specifier.startsWith('./')); return load(specifier.slice(2) + '.ets');
      } }, { timeout: 1000 });
      return module.exports;
    }
    return load;
  }
  function compare(label, calls, model, identities) {
    const actual = [0, -3, 7, -2147483648, 2147483647].flatMap(seed => {
      const token = new model.Token(seed);
      return [String(calls.crossFileCase(seed)), String(calls.identityCase(seed)), String(identities.keep(token) === token)];
    });
    result.comparisons.push({ label, expected: result.expected, actual }); record();
    assert.deepEqual(actual, result.expected);
  }
  const load = loader(texts);
  compare('multi-file', load('Calls.ets'), load('Trace.ets'), load('AInt.ets'));
  const flat = loader(new Map([['Combined.ets', readFileSync(join(forward, 'Combined.ets'), 'utf8')]]))('Combined.ets');
  compare('flat', flat, flat, flat);
  const privateSources = ['PrivateLeft.kt', 'PrivateRight.kt', 'PrivateCalls.kt', 'PrivateUnrelated.kt'].map(name => join(fixtures, 'private', name));
  const privateOracle = join(work, 'private-oracle.jar');
  run('private-oracle-build', 'bash', [compiler, ...privateSources, join(fixtures, 'private/PrivateOracle.kt'), '-d', privateOracle]);
  const privateExpected = run('private-oracle', 'java', ['-cp', `${privateOracle}:${cp}`, 'privateoverloads.PrivateOracleKt'])
    .stdout.trimEnd().split('\n');
  assert.equal(privateExpected.length, 5);
  const privateForward = join(work, 'private-forward'), privateReverse = join(work, 'private-reverse');
  for (const [label, destination, paths] of [
    ['private-forward', privateForward, privateSources], ['private-reverse', privateReverse, privateSources.toReversed()],
  ]) {
    mkdirSync(destination);
    const privateProbe = run(label, 'java', ['-cp', `${jar}:${cp}`, 'dev.ets.CrossFileProbeKt', cp, destination,
      privateBaseline ? 'private-baseline' : 'private', ...paths], privateBaseline ? 1 : 0);
    if (privateBaseline) {
      assert.match(privateProbe.stderr, /Conflicting module binding: pick/);
      assert.ok(existsSync(join(destination, 'actual.ir')));
      assert.equal(existsSync(join(destination, 'modules')), false);
      result.privateExpected = privateExpected;
      result.expectedRejection = 'Conflicting module binding: pick';
      guard(); result.passed = true; record();
      console.log('PASS expected RED: original private-scope JVM oracle succeeds, resolved public pick import collides before output');
      process.exit(0);
    }
  }
  const privateOutputs = readdirSync(join(privateForward, 'modules')).sort();
  assert.deepEqual(privateOutputs, privateSources.map(path => basename(path).replace(/\.kt$/, '.ets')).sort());
  result.privateModules = privateOutputs.map(name => {
    const path = join(privateForward, 'modules', name), sha256 = hash(path);
    assert.equal(sha256, hash(join(privateReverse, 'modules', name)), `Private input-order drift: ${name}`);
    return { path, sha256 };
  });
  const privateTexts = new Map(privateOutputs.map(name => [name, readFileSync(join(privateForward, 'modules', name), 'utf8')]));
  checkImports(privateTexts);
  const privateLoad = loader(privateTexts);
  for (const name of ['PrivateLeft.ets', 'PrivateRight.ets']) assert.equal(privateLoad(name).localOffset, undefined);
  assert.equal(privateLoad('PrivateLeft.ets').privateOrPublic, undefined);
  assert.equal(typeof privateLoad('PrivateRight.ets').privateOrPublic, 'function');
  const privateActual = [0, -3, 7, -2147483648, 2147483647].map(seed => String(privateLoad('PrivateCalls.ets').privateCase(seed)));
  result.comparisons.push({ label: 'private-multi-file', expected: privateExpected, actual: privateActual }); record();
  assert.deepEqual(privateActual, privateExpected);
  for (const [label, names, status, message] of [
    ['package-collision', ['LeftNames.kt', 'RightNames.kt', 'PackageCalls.kt'], 2, /Conflicting module binding/],
    ['filename-collision', ['left/Repeated.kt', 'right/Repeated.kt'], 2, /Source filenames collide/],
  ]) {
    const paths = names.map(name => join(fixtures, 'negative', name));
    run(label + '-jvm', 'bash', [compiler, ...paths, '-d', join(work, label + '.jar')]);
    const output = join(work, label);
    const failure = run(label, 'java', ['-cp', `${jar}:${cp}`, 'dev.ets.MainKt', '--mode', 'language', '--classpath', cp,
      '--out-dir', output, ...paths], status);
    const diagnostic = JSON.parse(failure.stdout);
    assert.equal(diagnostic.ok, false); assert.match(diagnostic.message, message); assert.equal(existsSync(output), false);
    if (label === 'package-collision') {
      assert.equal(diagnostic.code, 'INVALID_TARGET');
      assert.equal(diagnostic.source.file, paths[2]);
      assert.ok(diagnostic.source.start >= 0 && diagnostic.source.end > diagnostic.source.start);
    } else {
      assert.equal(diagnostic.code, 'INVALID_TARGET');
      assert.ok(paths.includes(diagnostic.source.file));
      for (const path of paths) assert.ok(diagnostic.message.includes(path));
    }
  }
  result.modules = outputs.map(name => ({ path: join(forward, 'modules', name), sha256: hash(join(forward, 'modules', name)) }));
}
guard(); result.passed = true; record();
console.log(baseline ? 'PASS expected RED: original JVM oracle succeeds, real cross-file module imports reject before output' :
  'PASS cross-file overloads: 15 JVM cases match module/flat output plus five private-scope module cases; exact IR identities, deterministic modules, two collision negatives; no SDK/native claim');
