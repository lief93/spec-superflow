import assert from 'node:assert/strict';
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync, existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../..');
mkdirSync(join(here, '.work'), { recursive: true });
const work = mkdtempSync(join(here, '.work/cli-'));
console.log(`Evidence: ${work}`);
function run(label, command, args, expected = 0) {
  const result = spawnSync(command, args, { encoding: 'utf8', timeout: 240000 });
  writeFileSync(join(work, label + '.json'), JSON.stringify({ command, args, status: result.status,
    stdout: result.stdout, stderr: result.stderr }, null, 2));
  assert.equal(result.error, undefined);
  assert.equal(result.status, expected, result.stdout + result.stderr);
  return result.stdout;
}
const sources = ['Functions.kt', 'Classes.kt', 'LocalGeneric.kt'].map(name => join(here, name));
const compiler = join(root, 'tests/stdlib/compiler.sh');
run('jvm-compile', 'bash', [compiler, '-d', join(work, 'oracle.jar'), ...sources, join(here, 'JvmOracle.kt')]);
const cp = run('classpath', 'bash', [compiler, '--classpath']).trim();
const expected = run('jvm', 'java', ['-cp', cp + ':' + join(work, 'oracle.jar'), 'genericfixture.JvmOracleKt']).trim().split('\n');
const output = join(work, 'Generics.ets');
run('generate', 'bash', [join(root, 'kotlin-ets'), '--mode', 'language', '--out', output, ...sources]);
const code = readFileSync(output, 'utf8');
const parsed = ts.createSourceFile(output, code, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
assert.deepEqual(parsed.parseDiagnostics, []);
const identity = parsed.statements.find(s => ts.isFunctionDeclaration(s) && s.name.text === 'identity');
assert.equal(identity.typeParameters[0].name.text, 'T');
assert.equal(identity.parameters[0].name.text, 'value');
assert.equal(identity.parameters[0].type.getText(parsed), 'T');
assert.equal(identity.type.getText(parsed), 'T');
const box = parsed.statements.find(s => ts.isClassDeclaration(s) && s.name.text === 'Box');
assert.equal(box.typeParameters[0].name.text, 'T');
assert.ok(box.members.some(ts.isGetAccessorDeclaration));
assert.ok(box.members.some(ts.isSetAccessorDeclaration));
const calls = [];
function visit(node) {
  if (ts.isFunctionDeclaration(node)) assert.ok(ts.isSourceFile(node.parent), 'no nested target declarations');
  if (ts.isArrowFunction(node)) assert.equal(node.typeParameters?.length ?? 0, 0, 'no generic arrows');
  if (ts.isCallExpression(node) && node.expression.getText(parsed) === 'choose') calls.push(node);
  ts.forEachChild(node, visit);
}
visit(parsed);
assert.ok(calls.some(call => call.arguments[1]?.getText(parsed) === 'undefined'), 'default arguments keep existing call form');
const compiled = ts.transpileModule(code, { compilerOptions: {
  target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS }, reportDiagnostics: true });
assert.deepEqual(compiled.diagnostics, []);
const context = { exports: {} };
vm.runInNewContext(compiled.outputText, context, { timeout: 1000 });
const actual = [-7, 0, 3, 29].flatMap(seed => [context.exports.functionCases(seed), context.exports.classCases(seed), context.exports.localCases(seed)]);
assert.deepEqual(actual, expected);
writeFileSync(join(work, 'comparison.json'), JSON.stringify({ expected, actual }, null, 2));
for (const name of ['Reified', 'Star', 'Variance']) {
  const rejected = join(work, name + '.ets');
  const diagnostic = JSON.parse(run(name, 'bash', [join(root, 'kotlin-ets'), '--mode', 'language', '--out', rejected,
    join(here, name + '.kt')], 2));
  assert.equal(diagnostic.code, 'UNSUPPORTED');
  assert.ok(diagnostic.source.start >= 0);
  assert.ok(!existsSync(rejected));
}
console.log(`PASS ${actual.length} same-source JVM/ETS generic cases, names/defaults/accessors/lifted locals and 3 fail-closed boundaries`);
