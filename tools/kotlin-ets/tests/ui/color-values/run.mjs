import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, writeFileSync, existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';
import { verifyEffects } from './effects.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../../..');
const work = mkdtempSync(join(tmpdir(), 'kotlin-ets-color-values-'));
const probe = process.env.KOTLIN_ETS_PROBE ?? '/tmp/kotlin-official-frontend-probe-06';
const cp = JSON.parse(readFileSync(join(probe, 'classpath.json'), 'utf8')).filter(existsSync);
const cpFile = join(work, 'classpath.txt');
writeFileSync(cpFile, cp.join('\n'));
console.log(`Evidence: ${work}`);
function run(label, command, args, expectedStatus = 0, environment = {}) {
  const result = spawnSync(command, args, { encoding: 'utf8', timeout: 600000,
    env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC', ...environment } });
  writeFileSync(join(work, `${label}.json`), JSON.stringify({ args, ...result }, null, 2));
  assert.equal(result.status, expectedStatus, result.stdout + result.stderr);
  return result.stdout;
}
const output = join(work, 'Models.ets');
run('language', 'bash', [join(root, 'kotlin-ets'), '--mode', 'language', '--classpath-file', cpFile,
  '--out', output, join(here, 'Models.kt')]);
const jar = join(work, 'oracle.jar');
run('jvm-build', 'bash', [join(root, 'tests/stdlib/compiler.sh'), '-classpath', cp.join(':'),
  join(here, 'Models.kt'), join(here, 'Oracle.kt'), '-d', jar]);
const expected = run('jvm', 'java', ['-cp', [jar, ...cp].join(':'), 'colorvalues.OracleKt']).trim().split('\n').map(Number);
const code = readFileSync(output, 'utf8');
const context = vm.createContext({ exports: {} });
vm.runInContext(ts.transpileModule(code, { compilerOptions: {
  target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS
} }).outputText, context, { timeout: 2000 });
const actual = Array.from(context.exports.observations());
assert.deepEqual(actual, expected);
writeFileSync(join(work, 'parity.json'), JSON.stringify({ expected, actual }, null, 2));
assert.match(code, /foreground: number \| null/);
assert.match(code, /foreground: number \| null = null/);
assert.match(code, /color: number \| null = null/);
assert.match(code, /color === null/);
run('page', 'bash', [join(root, 'kotlin-ets'), '--entry', 'colorvalues.Page', '--classpath-file', cpFile,
  '--out', join(work, 'Page.ets'), join(here, 'Models.kt'), join(here, 'Page.kt')]);
const page = readFileSync(join(work, 'Page.ets'), 'utf8');
assert.match(page, /Label\(value: number \| null = null\)/);
assert.match(page, /\.fontColor\(value \?\? 4278190080\)/);
assert.match(page, /\.fontColor\(4278190080\)/);
assert.match(page, /\.backgroundColor\([\s\S]*selectColor\(/);
assert.equal(page.split('selectColor(1, 4294967295, 4278190080)').length - 1, 1);
const effects = join(work, 'EffectPage.ets');
run('effect-page', 'bash', [join(root, 'kotlin-ets'), '--entry', 'colorvalues.EffectPage', '--classpath-file', cpFile,
  '--out', effects, join(here, 'EffectPage.kt')]);
verifyEffects(effects);
const unsupported = run('unsupported', 'bash', [join(root, 'kotlin-ets'), '--mode', 'language', '--classpath-file', cpFile,
  '--out', join(work, 'Unsupported.ets'), join(here, 'Unsupported.kt')], 2);
const unsupportedFailure = JSON.parse(unsupported.trim().split('\n').at(-1));
assert.match(unsupportedFailure.message, /Color\.toArgb requires a specified ARGB color/);
assert.equal(unsupportedFailure.source.line, 6);
assert.equal(existsSync(join(work, 'Unsupported.ets')), false);
const background = run('unsupported-background', 'bash', [join(root, 'kotlin-ets'), '--entry',
  'colorvalues.UnsupportedBackground', '--classpath-file', cpFile, '--out', join(work, 'UnsupportedBackground.ets'),
  join(here, 'Models.kt'), join(here, 'Page.kt')], 2);
const backgroundFailure = JSON.parse(background.trim().split('\n').at(-1));
assert.match(backgroundFailure.message, /Modifier\.background requires a specified ARGB color/);
assert.equal(backgroundFailure.source.line, 27);
assert.equal(existsSync(join(work, 'UnsupportedBackground.ets')), false);
const longExpression = run('long-expression', 'bash', [join(root, 'kotlin-ets'), '--mode', 'language',
  '--classpath-file', cpFile, '--out', join(work, 'LongExpression.ets'), join(here, 'LongExpression.kt')], 2);
assert.match(longExpression, /Unsupported external call: androidx.compose.ui.graphics.Color/);
assert.equal(existsSync(join(work, 'LongExpression.ets')), false);
const sdk = run('sdk', process.execPath, [join(here, '../basic-controls-sdk.mjs'), join(work, 'Page.ets')], 0, {
  KOTLIN_ETS_SDK_SEED: process.env.KOTLIN_ETS_SDK_SEED ?? '/private/tmp/kotlin-ets-basic-controls-sdk-bZjYXV/harmony',
});
process.stdout.write(sdk);
console.log('PASS optional Color defaults, explicit Unspecified, conditions, inherited Text, checked backgrounds, effects, JVM parity and SDK');
