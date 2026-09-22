import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../../..');
const parent = join(here, '.work');
mkdirSync(parent, { recursive: true });
const work = mkdtempSync(join(parent, 'run-'));
const output = join(work, 'ReactiveState.ets');
const hash = path => createHash('sha256').update(readFileSync(path)).digest('hex');
const result = { output, commands: [], passed: false, sdk: false };
const record = () => writeFileSync(join(work, 'result.json'), JSON.stringify(result, null, 2));
function run(label, command, args, env = process.env) {
  const observed = spawnSync(command, args, { cwd: root, env, encoding: 'utf8', timeout: 600000,
    maxBuffer: 32 * 1024 * 1024 });
  writeFileSync(join(work, `${label}.stdout`), observed.stdout ?? '');
  writeFileSync(join(work, `${label}.stderr`), observed.stderr ?? '');
  result.commands.push({ label, command, args, status: observed.status, error: observed.error?.message });
  record();
  assert.equal(observed.error, undefined);
  assert.equal(observed.status, 0, `${observed.stdout}\n${observed.stderr}`);
  return observed.stdout;
}

console.log(`Evidence: ${work}`);
record();
const fixture = join(root, 'tests/target/ReactiveStateTest.kt');
assert.doesNotMatch(readFileSync(fixture, 'utf8'), /Compose|Widget|remember|mutableStateOf/);
run('target-contract', 'bash', [join(root, 'tests/target/run.sh')],
  { ...process.env, KOTLIN_ETS_REACTIVE_STATE_FIXTURE: output });
assert.ok(existsSync(output));
result.outputSha256 = hash(output);
const code = readFileSync(output, 'utf8');
assert.match(code, /@State private count: number = 0;/);
assert.match(code, /Text\("count=" \+ this\.count\)/);
assert.match(code, /this\.count = this\.count \+ 1;/);
const sdkOutput = run('deveco', 'node', [join(root, 'tests/ui/basic-controls-sdk.mjs'), output]);
const sdkEvidence = sdkOutput.match(/^SDK evidence: (.+)$/m)?.[1];
assert.ok(sdkEvidence && existsSync(join(sdkEvidence, 'result.json')));
const sdk = JSON.parse(readFileSync(join(sdkEvidence, 'result.json'), 'utf8'));
assert.equal(sdk.passed, true);
assert.equal(sdk.sha256, result.outputSha256);
assert.equal(hash(output), result.outputSha256);
result.sdk = true;
result.sdkEvidence = sdkEvidence;
result.abc = sdk.abc;
result.haps = sdk.haps;
result.passed = true;
record();
console.log('PASS typed reactive state contract and unchanged generated @State component through DevEco ABC/HAP');
