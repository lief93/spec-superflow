import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';

const here = dirname(fileURLToPath(import.meta.url)), root = resolve(here, '../../..');
assert.ok(process.argv[2], 'Pass the unchanged GenericMethod interface fixture');
const input = resolve(process.argv[2]);
const hash = path => createHash('sha256').update(readFileSync(path)).digest('hex');
assert.equal(hash(input), '593e06ce5751bff7e7d29cc59d72926bfa4b3407988e683f2639827902e2243d',
  'The interface-only historical fixture must retain its original bytes');
mkdirSync(join(here, '.work'), { recursive: true });
const work = mkdtempSync(join(here, '.work/interface-')); console.log(`Evidence: ${work}`);
const implementation = readdirSync(join(root, 'src'), { recursive: true }).filter(path => path.endsWith('.kt'))
  .map(path => join(root, 'src', path)).sort();
const result = { inputs: [...implementation, input, fileURLToPath(import.meta.url), join(root, 'kotlin-ets')]
  .map(path => ({ path, sha256: hash(path) })), commands: [], scope: 'interface declaration only; no source runtime body' };
const record = () => writeFileSync(join(work, 'result.json'), JSON.stringify(result, null, 2));
const env = { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' };
function run(label, command, args) {
  const value = spawnSync(command, args, { env, encoding: 'utf8', timeout: 600000, maxBuffer: 16 * 1024 * 1024 });
  writeFileSync(join(work, label + '.stdout'), value.stdout ?? '');
  writeFileSync(join(work, label + '.stderr'), value.stderr ?? '');
  result.commands.push({ label, command, args, cwd: process.cwd(), status: value.status }); record();
  assert.equal(value.error, undefined); assert.equal(value.status, 0, value.stdout + value.stderr);
  return value.stdout;
}
const jar = join(work, 'original.jar'), output = join(work, 'GenericMethod.ets');
run('original-jvm', 'bash', [join(root, 'tests/stdlib/compiler.sh'), input, '-d', jar]);
assert.ok(existsSync(jar));
const response = JSON.parse(run('public-cli', 'bash', [join(root, 'kotlin-ets'), '--mode', 'language', '--out', output, input]));
assert.equal(response.ok, true); assert.equal(response.frontend, 'Kotlin-2.1.20-K2-FIR2IR');
const tree = ts.createSourceFile(output, readFileSync(output, 'utf8'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
assert.deepEqual(tree.parseDiagnostics, []);
assert.equal(tree.statements.length, 1);
const declaration = tree.statements[0];
assert.ok(ts.isInterfaceDeclaration(declaration)); assert.equal(declaration.name.text, 'GenericMethod');
assert.equal(declaration.typeParameters?.length ?? 0, 0);
assert.equal(declaration.members.length, 1);
const method = declaration.members[0];
assert.ok(ts.isMethodSignature(method)); assert.equal(method.name.text, 'read');
assert.equal(method.body, undefined); assert.equal(method.typeParameters.length, 1);
const binder = method.typeParameters[0];
assert.equal(binder.name.text, 'T'); assert.equal(binder.constraint, undefined); assert.equal(binder.default, undefined);
assert.equal(method.parameters.length, 1);
const parameter = method.parameters[0];
assert.equal(parameter.name.text, 'value'); assert.equal(parameter.questionToken, undefined);
assert.equal(parameter.dotDotDotToken, undefined); assert.equal(parameter.initializer, undefined);
for (const type of [parameter.type, method.type]) {
  assert.ok(ts.isTypeReferenceNode(type) && ts.isIdentifier(type.typeName));
  assert.equal(type.typeName.text, 'T'); assert.equal(type.typeArguments?.length ?? 0, 0);
}
for (const original of result.inputs) assert.equal(hash(original.path), original.sha256, `Changed during proof: ${original.path}`);
result.output = { path: output, sha256: hash(output) };
result.assertions = ['original JVM compilation', 'one GenericMethod interface', 'read method-owned T binder', 'value: T', 'result: T', 'no runtime body'];
result.passed = true; record();
console.log('PASS original interface JVM compilation and public AST signature proof; no runtime behavior claimed');
