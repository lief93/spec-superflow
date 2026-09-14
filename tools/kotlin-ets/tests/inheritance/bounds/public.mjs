import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';

const here = dirname(fileURLToPath(import.meta.url)), root = resolve(here, '../../..');
assert.ok(process.argv[2], 'Pass the successful focused probe result.json containing same-input JVM results');
const focusedPath = resolve(process.argv[2]), focused = JSON.parse(readFileSync(focusedPath));
assert.equal(focused.passed, true); assert.equal(focused.expected.length, 40);
const hash = path => createHash('sha256').update(readFileSync(path)).digest('hex');
for (const input of focused.inputs) assert.equal(hash(input.path), input.sha256, `Changed since JVM/probe run: ${input.path}`);
mkdirSync(join(here, '.work'), { recursive: true });
const work = mkdtempSync(join(here, '.work/public-'));
console.log(`Evidence: ${work}`);
const source = join(here, 'BoundedReceivers.kt'), output = join(work, 'BoundedReceivers.ets');
const args = [join(root, 'kotlin-ets'), '--mode', 'language', '--out', output, source];
const env = { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' };
const result = { focusedPath, focusedSha256: hash(focusedPath), inputs: focused.inputs,
  expected: focused.expected, command: 'bash', args, cwd: process.cwd(), JAVA_TOOL_OPTIONS: env.JAVA_TOOL_OPTIONS };
const record = () => writeFileSync(join(work, 'result.json'), JSON.stringify(result, null, 2));
const cli = spawnSync('bash', args, { env, encoding: 'utf8', timeout: 600000, maxBuffer: 16 * 1024 * 1024 });
writeFileSync(join(work, 'cli.stdout'), cli.stdout ?? '');
writeFileSync(join(work, 'cli.stderr'), cli.stderr ?? '');
result.status = cli.status; record();
assert.equal(cli.error, undefined); assert.equal(cli.status, 0, cli.stdout + cli.stderr);
assert.equal(hash(output), focused.output.sha256, 'Public CLI must preserve the complete focused output bytes');
const compiled = ts.transpileModule(readFileSync(output, 'utf8'), {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS }, reportDiagnostics: true,
});
assert.deepEqual(compiled.diagnostics, []);
const context = vm.createContext({ exports: {} });
vm.runInContext(compiled.outputText, context, { timeout: 1000 });
result.actual = [];
for (const seed of [0, -3, 7, -2147483648, 2147483647]) {
  for (const name of ['interfaceCase', 'classCase', 'plainCase', 'ancestorCase', 'chainCase', 'identityCase', 'selfCase', 'orderCase']) {
    result.actual.push(String(vm.runInContext(`exports.${name}(${seed})`, context, { timeout: 1000 })));
  }
}
record(); assert.deepEqual(result.actual, result.expected);
for (const input of focused.inputs) assert.equal(hash(input.path), input.sha256, `Changed during CLI run: ${input.path}`);
result.output = { path: output, sha256: hash(output) }; result.passed = true; record();
console.log('PASS public CLI exact output identity and 40 same-input JVM/host bounded-dispatch cases');
