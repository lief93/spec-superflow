import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdirSync, mkdtempSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';

export function verify(here, packageName, names) {
  const root = resolve(here, '../../..');
  mkdirSync(join(here, '.work'), { recursive: true });
  const work = mkdtempSync(join(here, '.work/run-'));
  console.log(`Evidence: ${work}`);
  const hash = path => createHash('sha256').update(readFileSync(path)).digest('hex');
  const sources = names.map(name => join(here, name));
  const inputs = [...readdirSync(join(root, 'src'), { recursive: true }).filter(p => p.endsWith('.kt')).map(p => join(root, 'src', p)),
    ...sources, join(here, 'Oracle.kt'), join(here, 'run.mjs'), fileURLToPath(import.meta.url)].map(path => ({ path, sha256: hash(path) }));
  const result = { inputs, commands: [], passed: false, level: 'JVM/ETS host, not ArkVM execution' };
  const record = () => writeFileSync(join(work, 'result.json'), JSON.stringify(result, null, 2));
  function run(label, command, args) {
    const r = spawnSync(command, args, { encoding: 'utf8', timeout: 600000, maxBuffer: 16 * 1024 * 1024,
      env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' } });
    for (const stream of ['stdout', 'stderr']) writeFileSync(join(work, `${label}.${stream}`), r[stream] ?? '');
    result.commands.push({ label, command, args, status: r.status }); record();
    assert.equal(r.error, undefined); assert.equal(r.status, 0, r.stdout + r.stderr); return r.stdout;
  }
  try {
    const compiler = join(root, 'tests/stdlib/compiler.sh'), cli = join(root, 'kotlin-ets');
    const cp = run('classpath', 'bash', [compiler, '--classpath']).trim(), jar = join(work, 'oracle.jar');
    run('jvm-build', 'bash', [compiler, ...sources, join(here, 'Oracle.kt'), '-d', jar]);
    result.expected = run('jvm', 'java', ['-cp', `${jar}:${cp}`, `${packageName}.OracleKt`]).trim().split('\n');
    const flat = join(work, 'Program.ets'), modules = join(work, 'modules'), reversed = join(work, 'reversed');
    run('flat', 'bash', [cli, '--mode', 'language', '--out', flat, ...sources]);
    run('modules', 'bash', [cli, '--mode', 'language', '--out-dir', modules, ...sources]);
    run('reversed', 'bash', [cli, '--mode', 'language', '--out-dir', reversed, ...sources.toReversed()]);
    const moduleNames = readdirSync(modules).sort();
    assert.deepEqual(moduleNames, readdirSync(reversed).sort());
    for (const name of moduleNames) assert.equal(readFileSync(join(modules, name), 'utf8'), readFileSync(join(reversed, name), 'utf8'));
    const options = { strict: true, noEmit: true, target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, types: [] };
    const files = [flat, ...moduleNames.map(p => join(modules, p))];
    const typed = files.map(path => { const target = path.replace(/\.ets$/, '.ts'); writeFileSync(target, readFileSync(path)); return target; });
    assert.deepEqual(ts.getPreEmitDiagnostics(ts.createProgram(typed, options)).map(d => ts.flattenDiagnosticMessageText(d.messageText, '\n')), []);
    function evaluate(entry) {
      const cache = new Map();
      function load(path) {
        if (cache.has(path)) return cache.get(path);
        const exports = {}; cache.set(path, exports);
        const code = ts.transpileModule(readFileSync(path, 'utf8'), { compilerOptions: options }).outputText;
        vm.runInNewContext(code, { exports, require: name => load(resolve(dirname(path), name + '.ets')) }, { timeout: 2000 });
        return exports;
      }
      return Array.from(load(entry).observations(), String);
    }
    result.actual = evaluate(flat); result.moduleActual = evaluate(join(modules, 'Application.ets'));
    assert.deepEqual(result.actual, result.expected); assert.deepEqual(result.moduleActual, result.expected);
    for (const input of inputs) assert.equal(hash(input.path), input.sha256);
    result.outputs = files.map(path => ({ path, sha256: hash(path) })); result.passed = true;
    console.log(`PASS ${result.actual.length} flat + module JVM/ETS results, strict host types and deterministic files`);
    return work;
  } finally { record(); }
}
