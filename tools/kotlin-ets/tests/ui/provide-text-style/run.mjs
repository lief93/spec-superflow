import assert from 'node:assert/strict';
import { existsSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../../..');
const work = mkdtempSync(join(tmpdir(), 'kotlin-ets-provide-text-style-'));
const probe = process.env.KOTLIN_ETS_PROBE ?? '/tmp/kotlin-official-frontend-probe-06';
const classpath = join(work, 'classpath.txt');
writeFileSync(classpath, JSON.parse(readFileSync(join(probe, 'classpath.json'), 'utf8')).join('\n'));
console.log(`Evidence: ${work}`);

function run(label, command, args, expected = 0, options = {}) {
  const result = spawnSync(command, args, { encoding: 'utf8', timeout: 600000,
    env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' }, ...options });
  writeFileSync(join(work, `${label}.json`), JSON.stringify({ command, args, status: result.status,
    stdout: result.stdout, stderr: result.stderr }, null, 2));
  assert.equal(result.status, expected, result.stdout + result.stderr);
  return result;
}

const output = join(work, 'Page.ets');
run('page', 'bash', [join(root, 'kotlin-ets'), '--mode', 'page', '--unsupported-policy', 'error',
  '--entry', 'providetextstyle.Page', '--classpath-file', classpath, '--out', output, join(here, 'Page.kt')]);
const code = readFileSync(output, 'utf8');
const textLine = label => code.split('\n').find(line => line.includes(`Text("${label}")`));

assert.match(code, /export class EtsMaterialContext[\s\S]*readonly textStyle: EtsTextStyle \| null;/);
assert.match(code, /export function __etsMergeTextStyle\(inherited: EtsTextStyle, provided: EtsTextStyle\): EtsTextStyle/);
assert.equal((code.match(/__etsMergeTextStyle\(/g) ?? []).length, 5,
  'two providers, two explicit Text styles, and the merge helper declaration');
assert.match(code, /Relay\(__etsMaterialContext: EtsMaterialContext, content: WrappedBuilder<\[EtsMaterialContext\]>/);
assert.match(code, /content\.builder\(__etsMaterialContext\)/);
assert.match(code, /SharedLabel\(__etsMaterialContext: EtsMaterialContext\)/);
assert.match(code, /SharedLabel\(new EtsMaterialContext\([\s\S]*?\.typography\.labelLarge,/,
  'the same source helper receives Button labelLarge at its invocation site');

for (const label of ['Theme body', 'Outer provider', 'Nested provider', 'Relayed', 'Shared', 'Restored']) {
  const line = textLine(label);
  assert.ok(line?.includes('__etsMaterialContext.textStyle ?? __etsMaterialContext.typography.bodyLarge'), line);
}
const explicitStyle = textLine('Explicit style');
assert.ok(explicitStyle?.includes('__etsMergeTextStyle(__etsMaterialContext.textStyle ?? '), explicitStyle);
const explicitField = textLine('Explicit field');
assert.ok(explicitField?.includes('__etsTextStyleModifier(null, 30.0,') &&
  explicitField.includes('__etsMergeTextStyle(__etsMaterialContext.textStyle ?? '), explicitField);

const styleStart = code.indexOf('export class EtsTextStyle {');
const styleEnd = code.indexOf('export class EtsTextStyleModifier');
assert.ok(styleStart >= 0 && styleEnd > styleStart);
const javascript = ts.transpileModule(code.slice(styleStart, styleEnd), { compilerOptions: {
  target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS,
}, reportDiagnostics: true });
assert.deepEqual(javascript.diagnostics, []);
const context = vm.createContext({ exports: {} });
vm.runInContext(javascript.outputText, context);
const { EtsTextStyle, __etsMergeTextStyle } = context.exports;
const inherited = new EtsTextStyle(1, 18, 400, null, null, 0.5, null, null, 24);
const outer = __etsMergeTextStyle(inherited, new EtsTextStyle(null, null, null, null, null, 1, null, null, 32));
const nested = __etsMergeTextStyle(outer, new EtsTextStyle(null, 22, null, null, null, null, null, null, null));
assert.deepEqual([nested.color, nested.fontSize, nested.fontWeight, nested.letterSpacing, nested.lineHeight],
  [1, 22, 400, 1, 32], 'nested scopes retain inherited fields and replace only provided fields');
const explicit = __etsMergeTextStyle(nested, new EtsTextStyle(null, null, 700, null, null, 2, null, null, null));
assert.deepEqual([explicit.color, explicit.fontSize, explicit.fontWeight, explicit.letterSpacing, explicit.lineHeight],
  [1, 22, 700, 2, 32], 'explicit Text style merges over the provider result');

const unsupportedSource = join(here, 'Unsupported.kt');
const failedOutput = join(work, 'Unsupported.ets');
const failed = run('unsupported', 'bash', [join(root, 'kotlin-ets'), '--mode', 'page', '--unsupported-policy', 'error',
  '--entry', 'providetextstyle.UnsupportedPage', '--classpath-file', classpath, '--out', failedOutput, unsupportedSource], 2);
const report = JSON.parse(failed.stdout.trim().split('\n').at(-1));
assert.equal(report.code, 'UNSUPPORTED');
assert.match(report.message, /Unsupported TextStyle argument: background/);
assert.equal(readFileSync(unsupportedSource, 'utf8').slice(report.source.start, report.source.end), 'Red');
assert.equal(report.source.line, 11);
assert.equal(report.source.column, 51);
assert.equal(existsSync(failedOutput), false);

const sdk = run('sdk', process.execPath, [join(here, '../basic-controls-sdk.mjs'), output], 0, {
  env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC',
    KOTLIN_ETS_SDK_SEED: process.env.KOTLIN_ETS_SDK_SEED ?? '/private/tmp/kotlin-ets-basic-controls-sdk-bZjYXV/harmony' },
});
assert.match(sdk.stdout, /PASS unmodified generated Page\.ets through actual SDK/);
console.log('PASS nested ProvideTextStyle scopes, slot forwarding, invocation context, precedence, diagnostics, and SDK');
