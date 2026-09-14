import assert from 'node:assert/strict';
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../..');
mkdirSync(join(here, '.work'), { recursive: true });
const work = mkdtempSync(join(here, '.work/accessors-'));
console.log(`Evidence: ${work}`);
function run(label, command, args) {
  const result = spawnSync(command, args, { encoding: 'utf8', timeout: 180000 });
  writeFileSync(join(work, label + '.json'), JSON.stringify({ command, args, status: result.status,
    stdout: result.stdout, stderr: result.stderr }, null, 2));
  assert.equal(result.error, undefined);
  assert.equal(result.status, 0, result.stdout + result.stderr);
  return result.stdout;
}
const output = join(work, 'AccessorSlice.ets');
run('generate', 'bash', [join(root, 'kotlin-ets'), '--mode', 'language', '--out', output, join(here, 'AccessorSlice.kt')]);
const code = readFileSync(output, 'utf8');
const parsed = ts.createSourceFile(output, code, ts.ScriptTarget.Latest, true);
assert.deepEqual(parsed.parseDiagnostics, []);
const reading = parsed.statements.find(s => ts.isClassDeclaration(s) && s.name.text === 'Reading');
assert.ok(reading);
assert.deepEqual(reading.members.filter(ts.isGetAccessorDeclaration).map(m => m.name.text), ['value', 'doubled', 'normalized']);
assert.deepEqual(reading.members.filter(ts.isSetAccessorDeclaration).map(m => m.name.text), ['value', 'normalized']);
assert.equal(reading.members.find(m => ts.isSetAccessorDeclaration(m) && m.name.text === 'value').parameters[0].name.text, 'next');
const compiled = ts.transpileModule(code, { compilerOptions: {
  target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS }, reportDiagnostics: true });
assert.deepEqual(compiled.diagnostics, []);
const context = { exports: {} };
vm.runInNewContext(compiled.outputText, context, { timeout: 1000 });
const compiler = join(root, 'tests/stdlib/compiler.sh');
run('jvm-compile', 'bash', [compiler, '-d', join(work, 'oracle.jar'), join(here, 'AccessorSlice.kt'), join(here, 'AccessorOracle.kt')]);
const cp = run('classpath', 'bash', [compiler, '--classpath']).trim();
const java = join(process.env.JAVA_HOME ?? '/Applications/Android Studio.app/Contents/jbr/Contents/Home', 'bin/java');
const expected = run('jvm', java, ['-cp', cp + ':' + join(work, 'oracle.jar'), 'accessorfixture.AccessorOracleKt']).trim().split('\n');
const actual = ['accessorSlice', 'accessorUpdate'].flatMap(name =>
  [0, 5, -2].flatMap(start => [-3, 0, 4].map(next => context.exports[name](start, next))));
assert.deepEqual(actual, expected, 'computed accessors, backing field, initialization and receiver effects must match Kotlin');
writeFileSync(join(work, 'comparison.json'), JSON.stringify({ expected, actual }, null, 2));
console.log(`PASS ${actual.length} JVM/ETS accessor cases; source property and setter parameter names retained`);
