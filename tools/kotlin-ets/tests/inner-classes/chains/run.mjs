import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { copyFileSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';

const here = dirname(fileURLToPath(import.meta.url)), root = resolve(here, '../../..');
const red = process.argv.includes('--red');
mkdirSync(join(here, '.work'), { recursive: true });
const work = mkdtempSync(join(here, red ? '.work/red-' : '.work/green-'));
console.log(`Evidence: ${work}`);
const hash = path => createHash('sha256').update(readFileSync(path)).digest('hex');
const paths = [...readdirSync(join(root, 'src'), { recursive: true }).filter(p => p.endsWith('.kt')).map(p => 'src/' + p),
  'tests/stdlib/compiler.sh', ...readdirSync(here, { recursive: true }).filter(p => !p.startsWith('.work') && (p.endsWith('.kt') || p === 'run.mjs')).map(p => 'tests/inner-classes/chains/' + p)].sort();
const inputs = paths.map(path => {
  const snapshot = join(work, 'frozen', path); mkdirSync(dirname(snapshot), { recursive: true });
  copyFileSync(join(root, path), snapshot); return { path, snapshot, sha256: hash(snapshot) };
});
const result = { work, red, inputs, commands: [], passed: false };
const record = () => writeFileSync(join(work, 'result.json'), JSON.stringify(result, null, 2));
function guard() { for (const input of inputs) { assert.equal(hash(join(root, input.path)), input.sha256); assert.equal(hash(input.snapshot), input.sha256); } }
function run(label, command, args) {
  guard(); const start = Date.now();
  const r = spawnSync(command, args, { cwd: root, env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' }, encoding: 'utf8', timeout: 600000, maxBuffer: 32 * 1024 * 1024 });
  writeFileSync(join(work, label + '.stdout'), r.stdout ?? ''); writeFileSync(join(work, label + '.stderr'), r.stderr ?? '');
  result.commands.push({ label, command, args, status: r.status, elapsedMs: Date.now() - start }); record();
  assert.equal(r.status, 0, r.stdout + r.stderr); guard(); return r.stdout;
}
const compiler = join(work, 'frozen/tests/stdlib/compiler.sh');
const fixtures = join(work, 'frozen/tests/inner-classes/chains');
const cp = run('classpath', 'bash', [compiler, '--classpath']).trim();
const files = ['Outer.kt', 'Peer.kt', 'Calls.kt'].map(p => join(fixtures, p));
run('oracle-build', 'bash', [compiler, ...files, join(fixtures, 'Oracle.kt'), '-d', join(work, 'oracle.jar')]);
result.expected = run('oracle', 'java', ['-cp', `${work}/oracle.jar:${cp}`, 'innerchains.OracleKt']).trimEnd().split('\n');
assert.equal(result.expected.length, 20);
run('backend-build', 'bash', [compiler, ...inputs.filter(i => i.path.startsWith('src/')).map(i => i.snapshot), join(fixtures, 'ChainsProbe.kt'), '-d', join(work, 'backend.jar')]);
const java = ['-cp', `${work}/backend.jar:${cp}`, 'dev.ets.chains.ChainsProbeKt', cp];
const output = join(work, 'output'); mkdirSync(output);
run('target', 'java', [...java, output, red ? 'red' : 'current', ...files]);
if (!red) {
  const reverse = join(work, 'reverse'); mkdirSync(reverse);
  run('reverse', 'java', [...java, reverse, 'current', ...files.toReversed()]);
  const names = readdirSync(join(output, 'modules')).sort();
  const texts = new Map(names.map(name => { assert.equal(hash(join(output, 'modules', name)), hash(join(reverse, 'modules', name))); return [name, readFileSync(join(output, 'modules', name), 'utf8')]; }));
  function verify(label, modules, entry) {
    const dir = join(work, label); mkdirSync(dir);
    for (const [name, text] of modules) writeFileSync(join(dir, name.replace(/\.ets$/, '.ts')), text);
    const program = ts.createProgram([...modules.keys()].map(n => join(dir, n.replace(/\.ets$/, '.ts'))), { strict: true, noEmit: true, target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, skipLibCheck: true });
    const diagnostics = ts.getPreEmitDiagnostics(program);
    writeFileSync(join(dir, 'diagnostics.txt'), ts.formatDiagnosticsWithColorAndContext(diagnostics, { getCanonicalFileName: x => x, getCurrentDirectory: () => dir, getNewLine: () => '\n' }));
    assert.equal(diagnostics.length, 0, readFileSync(join(dir, 'diagnostics.txt'), 'utf8'));
    const cache = new Map();
    function load(name) {
      if (cache.has(name)) return cache.get(name).exports;
      assert.ok(modules.has(name)); const module = { exports: {} }; cache.set(name, module);
      const code = ts.transpileModule(modules.get(name), { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } }).outputText;
      vm.runInNewContext(code, { module, exports: module.exports, require: specifier => load(specifier.slice(2) + '.ets') }, { timeout: 1000 }); return module.exports;
    }
    const actual = [0, -3, 7, -2147483648, 2147483647].flatMap(seed => load(entry).cases(seed).split('\n'));
    assert.deepEqual(actual, result.expected); writeFileSync(join(dir, 'actual.json'), JSON.stringify(actual));
  }
  verify('modules-check', texts, 'Calls.ets');
  verify('flat-check', new Map([['Combined.ets', readFileSync(join(output, 'Combined.ets'), 'utf8')]]), 'Combined.ets');
  const exclusions = { Anonymous: 'named source class', Derived: 'Any-only', GenericDeep: 'generic binders',
    GenericInner: 'generic binders', GenericRoot: 'generic binders', LocalOwner: 'top-level outer', Secondary: 'primary constructor', StaticOwner: 'top-level outer' };
  for (const [name, message] of Object.entries(exclusions)) {
    const dir = join(work, 'negative-' + name); mkdirSync(dir);
    run('negative-' + name, 'java', [...java, dir, message, join(fixtures, 'negative', name + '.kt')]);
  }
}
guard(); result.passed = true; record(); console.log(red ? 'PASS expected source-linked RED' : 'PASS chain identities, 20 JVM/flat/modules outcomes, semantic typecheck and deterministic modules');
