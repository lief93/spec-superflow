import assert from 'node:assert/strict';
import { copyFileSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { basename, dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';
import { compiler, harness, identities, root, sources, hash } from '../../binary-bodies/r2b/support.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const { work, run } = harness(join(here, '.work'));
const baseline = process.argv[2];
const inputs = identities([...(baseline ? [] : sources(join(root, 'src'))), join(here, 'Order.kt'), join(here, 'Oracle.kt'), fileURLToPath(import.meta.url)]);
const frozen = inputs.map(input => {
  const path = join(work, 'snapshot', relative(root, input.path));
  mkdirSync(dirname(path), { recursive: true });
  copyFileSync(input.path, path);
  assert.equal(hash(path), input.sha256);
  return path;
});
const cp = run('classpath', 'bash', [compiler, '--classpath']).trim();
process.env.KOTLIN_ETS_STDLIB = cp.split(':').find(path => basename(path) === 'kotlin-stdlib-2.1.20.jar');
assert.ok(process.env.KOTLIN_ETS_STDLIB);
const source = join(work, 'snapshot', relative(root, join(here, 'Order.kt')));
const oracle = join(work, 'oracle.jar');
run('original-build', 'bash', [compiler, source, join(dirname(source), 'Oracle.kt'), '-d', oracle]);
const expected = run('original-run', 'java', ['-cp', `${oracle}:${cp}`, 'classorder.OracleKt']).trim().split('\n');
const backend = baseline || join(work, 'backend.jar');
if (!baseline) run('backend-build', 'bash', [compiler, ...frozen.filter(path => path.includes('/snapshot/src/')), '-d', backend]);
const evidence = { passed: false, baseline: baseline ? { path: baseline, sha256: hash(baseline) } : null, inputs, expected, actual: [] };
for (const mode of ['flat', 'modules']) {
  const output = join(work, mode === 'flat' ? 'Order.ets' : 'modules');
  run(mode, 'java', ['-cp', `${backend}:${cp}`, 'dev.ets.MainKt', '--mode', 'language',
    mode === 'flat' ? '--out' : '--out-dir', output, source]);
  const file = mode === 'flat' ? output : join(output, 'Order.ets');
  const code = readFileSync(file, 'utf8');
  const parsed = ts.createSourceFile(file, code, ts.ScriptTarget.Latest, true);
  assert.deepEqual(parsed.parseDiagnostics, []);
  const compiled = ts.transpileModule(code, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } });
  const context = { exports: {} };
  if (baseline) {
    assert.throws(() => vm.runInNewContext(compiled.outputText, context), /before initialization/);
  } else {
    vm.runInNewContext(compiled.outputText, context, { timeout: 1000 });
    const actual = [-2, 0, 7, 2147483647].map(value => context.exports.result(value));
    assert.deepEqual(actual, expected);
    evidence.actual.push({ mode, values: actual, sha256: hash(file) });
  }
}
assert.ok(inputs.every(input => hash(input.path) === input.sha256), 'Sources changed during verification');
evidence.passed = true;
writeFileSync(join(work, 'result.json'), JSON.stringify(evidence, null, 2));
console.log(baseline ? 'PASS expected RED: JVM works; flat/modules base initialization fails' :
  'PASS JVM/flat/modules: nested bases, forward declarations and local inheritance');
