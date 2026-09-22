import assert from 'node:assert/strict';
import {existsSync, mkdtempSync, readFileSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {dirname, join, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../../..');
const work = mkdtempSync(join(tmpdir(), 'kotlin-ets-composition-local-'));
const probe = process.env.KOTLIN_ETS_PROBE ?? '/private/tmp/kotlin-official-frontend-probe-complete';
const classpath = join(work, 'classpath.txt');
writeFileSync(classpath, JSON.parse(readFileSync(join(probe, 'classpath.json'), 'utf8')).join('\n'));
console.log(`Evidence: ${work}`);

function compile(label, source, entry, expected = 0, preflight = false) {
  const output = join(work, `${label}.ets`);
  const report = join(work, `${label}-preflight.json`);
  const args = [join(root, 'kotlin-ets'), '--mode', 'page', '--unsupported-policy', 'error',
    '--entry', entry, '--classpath-file', classpath, '--out', output];
  if (preflight) args.push('--preflight-out', report);
  args.push(join(here, source));
  const result = spawnSync('bash', args, {encoding: 'utf8', timeout: 600000,
    env: {...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC'}});
  writeFileSync(join(work, `${label}.json`), JSON.stringify({args, status: result.status,
    stdout: result.stdout, stderr: result.stderr}, null, 2));
  assert.equal(result.status, expected, result.stdout + result.stderr);
  assert.equal(existsSync(output), expected === 0, `${label} partial ETS`);
  return {code: expected === 0 ? readFileSync(output, 'utf8') : null,
    failure: expected === 0 ? null : JSON.parse(result.stdout.trim().split('\n').at(-1)),
    preflight: existsSync(report) ? JSON.parse(readFileSync(report, 'utf8')) : null,
    output};
}

const page = compile('page', 'Page.kt', 'compositionlocal.Page', 0, true);
const code = page.code;
assert.match(code, /export class EtsCompositionContext \{[\s\S]*readonly local0: \(\(\) => number\);[\s\S]*readonly local1: \(\(\) => string\);[\s\S]*readonly local2: \(\(\) => Accent\);/);
assert.match(code, /Reading\(__etsCompositionContext: EtsCompositionContext, __etsMaterialContext: EtsMaterialContext, label: string\)/);
assert.match(code, /Relay\(__etsCompositionContext: EtsCompositionContext, __etsMaterialContext: EtsMaterialContext, content: WrappedBuilder<\[EtsCompositionContext, EtsMaterialContext\]>/);
assert.match(code, /content\.builder\(__etsCompositionContext, __etsMaterialContext\)/);
assert.match(code, /__etsCompositionContext\.local0\(\).*__etsCompositionContext\.local1\(\).*__etsCompositionContext\.local2\(\)\.label/);
assert.match(code, /this\.CompositionLocalContent_[0-9]+\(__etsCompositionContext, __etsMaterialContext, counted\(1\), named\("outer"\), accented\("blue"\)\)/);
assert.equal((code.match(/counted\(1\)/g) ?? []).length, 1);
assert.equal((code.match(/named\("outer"\)/g) ?? []).length, 1);
assert.equal((code.match(/accented\("blue"\)/g) ?? []).length, 1);
assert.ok(code.indexOf('counted(1)') < code.indexOf('named("outer")') &&
  code.indexOf('named("outer")') < code.indexOf('accented("blue")'),
  'provider values must evaluate once from left to right');
assert.match(code, /CompositionLocalContent_[0-9]+\(new EtsCompositionContext\([\s\S]*?counted\(2\)\)/);
assert.match(code, /new EtsCompositionContext\(\(\): number => \{\s*return __etsProvidedValue0;[\s\S]*?__etsCompositionContext\.local1, __etsCompositionContext\.local2\)/,
  'nested override must retain non-overridden outer locals');
assert.match(code, /Reading\(__etsCompositionContext, __etsMaterialContext, "restored-default"\)/);
assert.match(code, /new EtsCompositionContext\(\(\): number => \{\s*return -1;[\s\S]*?return "default";[\s\S]*?return new Accent\("none"\);/,
  'root context must retain lazy typed defaults');

const calls = page.preflight.calls;
const providers = calls.filter(call => call.finalRecognizedNode.symbol ===
  'androidx.compose.runtime.CompositionLocalProvider');
assert.equal(providers.length, 2);
assert.ok(providers.every(call => call.expectedTargetType === 'void' &&
  call.finalRecognizedNode.kind === 'typed_call' && call.firstUnsupportedNode === null));
const provided = calls.filter(call => call.finalRecognizedNode.symbol ===
  'androidx.compose.runtime.ProvidableCompositionLocal.provides');
assert.equal(provided.length, 4);
assert.ok(provided.every(call => call.expectedTargetType?.startsWith('EtsProvidedValue<') &&
  call.finalRecognizedNode.kind === 'typed_call' && call.firstUnsupportedNode === null));
const current = calls.filter(call => call.finalRecognizedNode.symbol ===
  'androidx.compose.runtime.ProvidableCompositionLocal.<get-current>');
assert.equal(current.length, 3);
assert.ok(current.every(call => call.expectedTargetType !== null && call.firstUnsupportedNode === null));

const unsupported = compile('unsupported', 'Unsupported.kt',
  'compositionlocal.unsupported.UnsupportedPage', 2, true).failure;
assert.equal(unsupported.code, 'UNSUPPORTED');
assert.match(unsupported.message, /Unsupported language type: androidx\.compose\.ui\.unit\.Density/);
assert.equal(resolve(unsupported.source.file), resolve(join(here, 'Unsupported.kt')));
assert.equal(unsupported.source.line, 12);
assert.equal(unsupported.source.column, 23);
assert.equal(readFileSync(join(here, 'Unsupported.kt'), 'utf8').slice(unsupported.source.start,
  unsupported.source.end), 'current');

const sdk = spawnSync(process.execPath, [join(here, '../basic-controls-sdk.mjs'), page.output], {
  encoding: 'utf8', timeout: 600000,
  env: {...process.env, KOTLIN_ETS_SDK_SEED:
    process.env.KOTLIN_ETS_SDK_SEED ?? '/private/tmp/kotlin-ets-basic-controls-sdk-bZjYXV/harmony'},
});
writeFileSync(join(work, 'sdk.json'), JSON.stringify({status: sdk.status, stdout: sdk.stdout,
  stderr: sdk.stderr}, null, 2));
assert.equal(sdk.status, 0, sdk.stdout + sdk.stderr);
console.log(sdk.stdout.trim());
console.log('PASS typed CompositionLocal declarations, defaults/current, ordered vararg providers, nested overrides, dual-context slot forwarding, source-linked rejection and SDK');
