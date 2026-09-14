// Run after production freeze. Host parity is separate from native SDK/device proof.
import assert from 'node:assert/strict';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';
import { compiler, harness, identities, root, sources, hash } from '../r2b/support.mjs';

const here = dirname(fileURLToPath(import.meta.url));
assert.ok(process.argv[2], 'Pass a completed focused member-inline directory');
const producer = resolve(process.argv[2]);
const complete = JSON.parse(readFileSync(join(producer, 'complete.json')));
const inputs = JSON.parse(readFileSync(join(producer, 'producers.json')));
assert.ok(inputs.every(input => hash(input.path) === input.sha256), 'Producer binaries changed');
assert.equal(existsSync(join(producer, 'producer-source')), false);
const { work, run } = harness(producer, 'replay-');
const production = sources(join(root, 'src'));
const implementation = identities([...production, join(here, 'Replay.kt'), join(here, 'Receivers.ets'), complete.application]);
const cp = run('classpath', 'bash', [compiler, '--classpath']).trim();
const jar = join(work, 'replay.jar');
run('compile', 'bash', [compiler, ...production, join(here, 'Replay.kt'), '-d', jar]);
const classpath = `${cp}:${join(producer, 'members.jar')}`;
const expected = run('jvm', 'java', ['-cp', `${classpath}:${join(producer, 'oracle.jar')}`,
  'memberconsumer.OracleKt']).trim().split('\n');
const output = join(work, 'Application.ets');
run('generate-with-explicit-type-adapter', 'java', ['-cp', `${cp}:${jar}`, 'dev.ets.r2e.ReplayKt',
  classpath, complete.application, output]);
const code = readFileSync(output, 'utf8');
const parsed = ts.createSourceFile('Application.ets', code, ts.ScriptTarget.Latest, true);
assert.deepEqual(parsed.parseDiagnostics, []);
const scenario = parsed.statements.find(node => ts.isFunctionDeclaration(node) && node.name.text === 'scenario');
assert.deepEqual(scenario.parameters.map(parameter => parameter.name.text), ['receiver', 'peer', 'seed']);
assert.equal(parsed.statements.some(node => ts.isClassDeclaration(node) && ['FinalMember', 'PeerMember'].includes(node.name.text)), false);
function execute(source, require) {
  const compiled = ts.transpileModule(source, { compilerOptions: {
    target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS }, reportDiagnostics: true });
  assert.deepEqual(compiled.diagnostics, []);
  const context = { exports: {}, require };
  vm.runInNewContext(compiled.outputText, context, { timeout: 1000 });
  return context.exports;
}
const receivers = execute(readFileSync(join(here, 'Receivers.ets'), 'utf8'), () => assert.fail('Unexpected receiver import'));
const target = execute(code, name => {
  assert.equal(name, './Receivers');
  return receivers;
});
const actual = [1, -2, 2147483647].map(seed => target.scenario(new receivers.FinalMember(), new receivers.PeerMember(), seed));
assert.deepEqual(actual, expected);
// The command-line compiler cannot invent the external receiver's target type.
const unavailable = join(work, 'unmapped.ets');
const rejection = JSON.parse(run('unmapped-cli', 'java', ['-cp', `${cp}:${jar}`, 'dev.ets.MainKt', '--mode', 'language',
  '--classpath', classpath, '--out', unavailable, complete.application], 2));
assert.ok(['UNSUPPORTED', 'INVALID_TARGET'].includes(rejection.code));
assert.equal(existsSync(unavailable), false);
assert.ok(implementation.every(input => hash(input.path) === input.sha256), 'Production changed during replay');
writeFileSync(join(work, 'result.json'), JSON.stringify({ passed: true, expected, actual, output, sha256: hash(output),
  implementation, producerInputs: inputs, receiverTypes: 'explicit CallRule and test-host types; not class translation',
  unmappedCli: rejection, sdk: 'not run', device: 'not run' }, null, 2));
console.log(`PASS ${actual.length} JVM/host member-inline pairs with explicit receiver type mapping; unmapped CLI rejects`);
