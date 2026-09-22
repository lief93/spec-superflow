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
const work = mkdtempSync(join(tmpdir(), 'kotlin-ets-line-height-style-'));
const probe = process.env.KOTLIN_ETS_PROBE ?? '/tmp/kotlin-official-frontend-probe-06';
const cp = JSON.parse(readFileSync(join(probe, 'classpath.json'), 'utf8')).filter(existsSync);
const cpFile = join(work, 'classpath.txt');
writeFileSync(cpFile, cp.join('\n'));
console.log(`Evidence: ${work}`);

function run(label, command, args, expected = 0, options = {}) {
  const result = spawnSync(command, args, { encoding: 'utf8', timeout: 600000,
    env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' }, ...options });
  writeFileSync(join(work, `${label}.json`), JSON.stringify({ command, args, status: result.status,
    stdout: result.stdout, stderr: result.stderr }, null, 2));
  assert.equal(result.status, expected, result.stdout + result.stderr);
  return result;
}

const modelOutput = join(work, 'Models.ets');
run('language', 'bash', [join(root, 'kotlin-ets'), '--mode', 'language', '--classpath-file', cpFile,
  '--out', modelOutput, join(here, 'Models.kt'), join(here, 'Consumer.kt')]);
const modelCode = readFileSync(modelOutput, 'utf8');
assert.match(modelCode, /export class EtsLineHeightAlignment/);
assert.match(modelCode, /export class EtsLineHeightTrim/);
assert.match(modelCode, /export class EtsLineHeightMode/);
assert.match(modelCode, /export class EtsLineHeightStyle/);
assert.doesNotMatch(modelCode, /alignment: (?:string|number)|trim: (?:string|number)|mode: (?:string|number)/);
const target = vm.createContext({ exports: {} });
vm.runInContext(ts.transpileModule(modelCode, { compilerOptions: {
  target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS,
} }).outputText, target, { timeout: 2000 });
const actual = [...target.exports.semanticSnapshot(),
  target.exports.heldCode(target.exports.hold(target.exports.makeLegacyStyle(
    target.exports.__etsLineHeightAlignmentTop, target.exports.__etsLineHeightTrimBoth)))];

const oracleJar = join(work, 'oracle.jar');
run('jvm-build', 'bash', [join(root, 'tests/stdlib/compiler.sh'), '-classpath', cp.join(':'),
  join(here, 'Models.kt'), join(here, 'Consumer.kt'), join(here, 'Oracle.kt'), '-d', oracleJar]);
const expected = run('jvm', 'java', ['-cp', [oracleJar, ...cp].join(':'), 'lineheightstyle.OracleKt'])
  .stdout.trim().split('\n').map(Number);
assert.deepEqual(actual, expected);
writeFileSync(join(work, 'parity.json'), JSON.stringify({ expected, actual }, null, 2));

const modules = join(work, 'modules');
run('modules', 'bash', [join(root, 'kotlin-ets'), '--mode', 'language', '--classpath-file', cpFile,
  '--out-dir', modules, join(here, 'Models.kt'), join(here, 'Consumer.kt')]);
for (const name of ['Models', 'Consumer']) {
  const code = readFileSync(join(modules, `${name}.ets`), 'utf8');
  assert.match(code, /from ['"]\.\/EtsLineHeightStyle['"]/);
  assert.doesNotMatch(code, /class EtsLineHeightStyle/);
}

const supportedOutput = join(work, 'SupportedPage.ets');
run('supported-page', 'bash', [join(root, 'kotlin-ets'), '--mode', 'page', '--unsupported-policy', 'error',
  '--entry', 'lineheightstyle.SupportedPage', '--classpath-file', cpFile, '--out', supportedOutput,
  join(here, 'Page.kt')]);
const supportedCode = readFileSync(supportedOutput, 'utf8');
assert.match(supportedCode, /halfLeading\(true\)/);
assert.match(supportedCode, /lineHeightStyle/);

const pageOutput = join(work, 'Page.ets');
run('page-report', 'bash', [join(root, 'kotlin-ets'), '--mode', 'page', '--unsupported-policy', 'report',
  '--entry', 'lineheightstyle.Page', '--classpath-file', cpFile, '--out', pageOutput, join(here, 'Page.kt')]);
const diagnosis = JSON.parse(readFileSync(`${pageOutput}.diagnosis.json`, 'utf8'));
assert.equal(diagnosis.status, 'generated_with_degradations');
assert.ok(diagnosis.degradations.length >= 2);
for (const item of diagnosis.degradations) {
  assert.equal(item.capability, 'compose.text.line_height_style');
  assert.equal(item.action, 'line_height_style_fallback');
  assert.match(item.message, /LineHeightStyle/);
  assert.equal(item.source.file.endsWith('/Page.kt') || item.source.file === join(here, 'Page.kt'), true);
}
const pageCode = readFileSync(pageOutput, 'utf8');
assert.match(pageCode, /if \([^\n]*lineHeightStyle/);
assert.match(pageCode, /\.lineHeight\(/);

const strictOutput = join(work, 'Strict.ets');
const strict = run('page-strict', 'bash', [join(root, 'kotlin-ets'), '--mode', 'page', '--unsupported-policy', 'error',
  '--entry', 'lineheightstyle.Page', '--classpath-file', cpFile, '--out', strictOutput, join(here, 'Page.kt')], 2);
const strictReport = JSON.parse(strict.stdout.trim().split('\n').at(-1));
assert.equal(strictReport.code, 'UNSUPPORTED');
assert.match(strictReport.message, /LineHeightStyle/);
assert.match(readFileSync(join(here, 'Page.kt'), 'utf8').slice(strictReport.source.start, strictReport.source.end), /Text\(/);

const misuseOutput = join(work, 'Misuse.ets');
const misuse = run('misuse', 'bash', [join(root, 'kotlin-ets'), '--mode', 'language', '--classpath-file', cpFile,
  '--out', misuseOutput, join(here, 'Misuse.kt')], 2);
const misuseReport = JSON.parse(misuse.stdout.trim().split('\n').at(-1));
assert.equal(misuseReport.code, 'UNSUPPORTED');
assert.match(misuseReport.message, /hashCode|Unsupported external call/);
assert.equal(readFileSync(join(here, 'Misuse.kt'), 'utf8').slice(misuseReport.source.start, misuseReport.source.end),
  'hashCode()');

const customOutput = join(work, 'CustomAlignment.ets');
const custom = run('custom-alignment', 'bash', [join(root, 'kotlin-ets'), '--mode', 'language',
  '--classpath-file', cpFile, '--out', customOutput, join(here, 'CustomAlignment.kt')], 2);
const customReport = JSON.parse(custom.stdout.trim().split('\n').at(-1));
assert.equal(customReport.code, 'UNSUPPORTED');
assert.match(customReport.message, /published LineHeightStyle values/);
assert.match(readFileSync(join(here, 'CustomAlignment.kt'), 'utf8')
  .slice(customReport.source.start, customReport.source.end), /Alignment\(0\.25f\)|constructor/);

const sdk = run('sdk', process.execPath, [join(here, '../basic-controls-sdk.mjs'), supportedOutput], 0, {
  env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC',
    KOTLIN_ETS_SDK_SEED: process.env.KOTLIN_ETS_SDK_SEED ?? '/private/tmp/kotlin-ets-basic-controls-sdk-bZjYXV/harmony' },
});
assert.match(sdk.stdout, /PASS unmodified generated SupportedPage\.ets through actual SDK/);
console.log('PASS LineHeightStyle values, construction, copies, equality, cross-file flow, Text mapping, degradation, misuse, and SDK');
