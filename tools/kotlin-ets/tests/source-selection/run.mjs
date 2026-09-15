import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdtempSync, readFileSync, readdirSync, writeFileSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';

const here = dirname(fileURLToPath(import.meta.url)), root = resolve(here, '../..');
const work = mkdtempSync(join(tmpdir(), 'kotlin-ets-source-selection-'));
console.log(`Evidence: ${work}`);
const result = { passed: false, commands: [], level: 'JVM/ETS host, not ArkVM execution' };
function run(label, command, args, status = 0) {
  const r = spawnSync(command, args, { encoding: 'utf8', timeout: 600000, maxBuffer: 16 * 1024 * 1024,
    env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' } });
  for (const stream of ['stdout', 'stderr']) writeFileSync(join(work, `${label}.${stream}`), r[stream] ?? '');
  result.commands.push({ label, command, args, status: r.status });
  assert.equal(r.error, undefined); assert.equal(r.status, status, r.stdout + r.stderr);
  return r;
}
try {
  const compiler = join(root, 'tests/stdlib/compiler.sh');
  const cp = run('classpath', 'bash', [compiler, '--classpath']).stdout.trim();
  const sources = ['Application.kt', 'Support.kt', 'Models.kt', 'Host.kt'].map(name => join(here, name));
  const tool = join(work, 'tool.jar');
  const implementation = readdirSync(join(root, 'src'), { recursive: true }).filter(p => p.endsWith('.kt')).sort().map(p => join(root, 'src', p));
  const hash = path => createHash('sha256').update(readFileSync(path)).digest('hex');
  result.inputs = [...implementation, ...sources, join(here, 'Oracle.kt'), fileURLToPath(import.meta.url)]
    .map(path => ({ path, sha256: hash(path) }));
  run('compiler', 'bash', [compiler, ...implementation, '-d', tool]);
  run('oracle-build', 'bash', [compiler, ...sources, join(here, 'Oracle.kt'), '-d', join(work, 'oracle.jar')]);
  result.expected = run('oracle', 'java', ['-cp', `${cp}:${join(work, 'oracle.jar')}`, 'selection.OracleKt']).stdout.trim().split('\n');
  function convert(label, entry, status = 0, input = sources, modules = false) {
    const output = join(work, label + (modules ? '' : '.ets'));
    const r = run(label, 'java', ['-cp', `${cp}:${tool}`, 'dev.ets.MainKt', '--mode', 'language',
      '--classpath', cp, ...(entry ? ['--entry', entry] : []), modules ? '--out-dir' : '--out', output, ...input], status);
    if (status) assert.equal(existsSync(output), false);
    return { ...r, output };
  }
  const selected = convert('selected', 'selection.observations');
  const report = r => JSON.parse(r.stderr.split('\n').find(line => line.startsWith('{"event":"source-selection"')));
  const selection = report(selected);
  assert(selection.excluded.some(d => d.symbol === 'selection.UnrelatedHost'));
  assert(selection.kept.some(d => d.symbol === 'selection.registration'));
  assert(selection.kept.some(d => d.symbol === 'selection.Label'));
  assert(selection.excluded.some(d => d.symbol === 'selection.modelFileRegistration'));
  assert.equal(selection.kept.filter(d => d.symbol === 'selection.label').length, 1);
  assert.equal(selection.excluded.filter(d => d.symbol === 'selection.label').length, 1);
  const code = readFileSync(selected.output, 'utf8');
  assert.doesNotMatch(code, /UnrelatedHost|unrelatedRegistration|reachableFailure|unsupported\(/);
  assert.match(code, /function negative\(/);
  const options = { strict: true, noEmit: true, target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, types: [] };
  function evaluate(path) {
    const cache = new Map(), context = vm.createContext({});
    function load(file) {
      if (cache.has(file)) return cache.get(file);
      const exports = {}; cache.set(file, exports);
      const js = ts.transpileModule(readFileSync(file, 'utf8'), { compilerOptions: options }).outputText;
      vm.runInContext(`(function(exports, require) {\n${js}\n})`, context, { timeout: 2000 })(exports,
        name => load(resolve(dirname(file), name + '.ets')));
      return exports;
    }
    const api = load(path);
    const first = Array.from(api.observations(), String);
    assert.deepEqual(Array.from(api.observations(), String), first, 'File initialization must run only once');
    return first;
  }
  result.actual = evaluate(selected.output);
  assert.deepEqual(result.actual, result.expected);
  const modules = convert('modules', 'selection.observations', 0, sources.toReversed(), true);
  assert.deepEqual(evaluate(join(modules.output, 'Application.ets')), result.expected);
  const outputs = [selected.output, ...readdirSync(modules.output).filter(p => p.endsWith('.ets')).map(p => join(modules.output, p))];
  const typed = outputs.map(path => { const name = path.replace(/\.ets$/, '.ts'); writeFileSync(name, readFileSync(path)); return name; });
  assert.deepEqual(ts.getPreEmitDiagnostics(ts.createProgram(typed, options)).map(d => ts.flattenDiagnosticMessageText(d.messageText, '\n')), []);
  const rejected = convert('reachable-failure', 'selection.reachableFailure', 2);
  assert.match(rejected.stdout, /UNSUPPORTED/);
  assert(report(rejected).kept.some(d => d.symbol === 'selection.unsupported'));
  const reference = convert('reference-only', 'selection.referenceOnly', 2);
  assert(report(reference).kept.some(d => d.symbol === 'selection.defaultValue'));
  convert('whole-module', null, 2);
  assert.match(convert('missing', 'selection.absent', 1).stdout, /entry/i);
  assert.match(convert('ambiguous', 'selection.label', 1).stdout, /entry/i);
  const invalid = join(work, 'Invalid.kt');
  writeFileSync(invalid, 'package unrelated\nfun invalid(): Int = "not an Int"\n');
  assert.match(convert('invalid-source', 'selection.observations', 1, [...sources, invalid]).stdout, /Kotlin resolution failed/);
  for (const input of result.inputs) assert.equal(hash(input.path), input.sha256);
  result.outputs = outputs.map(path => ({ path, sha256: hash(path) }));
  result.passed = true;
  console.log('PASS selected flat/module JVM equivalence, strict types, defaults/references/initializers and failure boundaries');
} finally {
  writeFileSync(join(work, 'result.json'), JSON.stringify(result, null, 2));
}
