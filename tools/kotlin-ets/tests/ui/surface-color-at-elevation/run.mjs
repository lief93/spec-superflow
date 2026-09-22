import assert from 'node:assert/strict';
import {existsSync, mkdtempSync, readFileSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {dirname, join, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../../..');
const work = mkdtempSync(join(tmpdir(), 'kotlin-ets-surface-elevation-'));
const probe = process.env.KOTLIN_ETS_PROBE ?? '/private/tmp/kotlin-official-frontend-probe-complete';
const classpath = JSON.parse(readFileSync(join(probe, 'classpath.json'), 'utf8')).filter(existsSync);
const classpathFile = join(work, 'classpath.txt');
writeFileSync(classpathFile, classpath.join('\n') + '\n');
console.log(`Evidence: ${work}`);

function compile(label, mode, sources, entry, expected = 0) {
  const output = join(work, `${label}.ets`);
  const args = [join(root, 'kotlin-ets'), '--mode', mode, '--unsupported-policy', 'error'];
  if (entry) args.push('--entry', entry);
  args.push('--classpath-file', classpathFile, '--out', output, ...sources.map(source => join(here, source)));
  const result = spawnSync('bash', args, {encoding: 'utf8', timeout: 600000,
    env: {...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC'}});
  writeFileSync(join(work, `${label}.json`), JSON.stringify({args, status: result.status,
    stdout: result.stdout, stderr: result.stderr}, null, 2));
  assert.equal(result.status, expected, result.stdout + result.stderr);
  assert.equal(existsSync(output), expected === 0, `${label} partial ETS`);
  return expected === 0 ? readFileSync(output, 'utf8') : JSON.parse(result.stdout.trim().split('\n').at(-1));
}

const code = compile('models', 'language', ['Models.kt']);
assert.match(code, /export function elevated\(surface: number \| null, surfaceTint: number \| null, elevation: number \| null\): number \| null/);
assert.match(code, /surfaceColorAtElevation received Dp\.Unspecified/);
assert.match(code, /\)\(elevation\)\);/);
assert.match(code, /if \(elevation === 0 && 1 \/ elevation > 0\) \{\s*return scheme\.surface;/);
assert.ok(code.indexOf('if (elevation === 0') < code.indexOf('Math.log'), 'positive zero must return before logarithm');
assert.match(code, /scheme\.surfaceTint/);
assert.match(code, /ColorMetrics\.numeric\(scheme\.surface\)/);
assert.match(code, /__etsCopyColor\(scheme\.surfaceTint, alpha, null, null, null\)/);
assert.match(code, /Math\.fround/);

const parsed = ts.createSourceFile('models.ts', code, ts.ScriptTarget.ES2022, true);
const ordinary = parsed.statements.filter(node => !ts.isImportDeclaration(node))
  .map(node => node.getFullText(parsed)).join('\n');
const transpiled = ts.transpileModule(ordinary, {compilerOptions: {
  target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS,
}});
assert.deepEqual(transpiled.diagnostics ?? [], []);
const channels = value => ({alpha: Math.floor(value / 0x1000000) % 0x100,
  red: Math.floor(value / 0x10000) % 0x100, green: Math.floor(value / 0x100) % 0x100,
  blue: value % 0x100});
const ColorMetrics = {
  numeric: channels,
  rgba(red, green, blue, alpha = 1) {
    return {red, green, blue, alpha: Math.floor(alpha * 255 + 0.5)};
  },
};
const context = vm.createContext({exports: {}, ColorMetrics});
vm.runInContext(transpiled.outputText, context);
const cases = [
  [0xFF203040, 0xFFE08020, 0],
  [0xFF203040, 0xFFE08020, -0],
  [0xFF203040, 0xFFE08020, 2],
  [0xFF203040, 0xFFE08020, 8],
  [0x80402010, 0xC0E08040, 2],
  [0x80402010, 0xC0E08040, 24],
  [0x00000000, 0xFFFFFFFF, 2],
];
const hex = value => value.toString(16).padStart(8, '0');
const actual = cases.map(args => hex(context.exports.elevated(...args)));
context.exports.resetEvaluationTrace();
actual.push(hex(context.exports.orderedColor()), context.exports.currentEvaluationTrace());

const oracleJar = join(work, 'oracle.jar');
const oracleCompile = spawnSync('bash', [join(root, 'tests/stdlib/compiler.sh'), '-classpath',
  classpath.join(':'), join(here, 'Models.kt'), join(here, 'Oracle.kt'), '-d', oracleJar],
{encoding: 'utf8', timeout: 600000, env: {...process.env,
  JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC'}});
writeFileSync(join(work, 'oracle-compile.json'), JSON.stringify({status: oracleCompile.status,
  stdout: oracleCompile.stdout, stderr: oracleCompile.stderr}, null, 2));
assert.equal(oracleCompile.status, 0, oracleCompile.stdout + oracleCompile.stderr);
const oracle = spawnSync('java', ['-cp', [oracleJar, ...classpath].join(':'), 'surfaceelevation.OracleKt'],
  {encoding: 'utf8', timeout: 600000});
writeFileSync(join(work, 'oracle.json'), JSON.stringify({status: oracle.status,
  stdout: oracle.stdout, stderr: oracle.stderr}, null, 2));
assert.equal(oracle.status, 0, oracle.stdout + oracle.stderr);
const expected = oracle.stdout.trim().split('\n');
assert.deepEqual(actual, expected, 'generated runtime must match official Material3/Compose behavior');
assert.equal(actual.at(-1), 'receiver:elevation', 'receiver and elevation must each evaluate once in source order');

const unsupported = compile('unsupported', 'page', ['Unsupported.kt'],
  'surfaceelevation.unsupported.Page', 2);
assert.equal(unsupported.code, 'UNSUPPORTED');
assert.match(unsupported.message, /surfaceColorAtElevation requires a specified Dp value/);
assert.equal(resolve(unsupported.source.file), resolve(join(here, 'Unsupported.kt')));
assert.ok(unsupported.source.line > 0 && unsupported.source.column > 0);

const page = compile('page', 'page', ['Models.kt', 'Page.kt'], 'surfaceelevation.Page');
assert.match(page, /\.fontColor\(__etsSurfaceColorAtElevation\(colors, \(\(dimension: number \| null\)/);
const sdk = spawnSync(process.execPath, [join(here, '../basic-controls-sdk.mjs'), join(work, 'page.ets')], {
  encoding: 'utf8', timeout: 600000,
  env: {...process.env, KOTLIN_ETS_SDK_SEED:
    process.env.KOTLIN_ETS_SDK_SEED ?? '/private/tmp/kotlin-ets-basic-controls-sdk-bZjYXV/harmony'},
});
writeFileSync(join(work, 'sdk.json'), JSON.stringify({status: sdk.status, stdout: sdk.stdout,
  stderr: sdk.stderr}, null, 2));
assert.equal(sdk.status, 0, sdk.stdout + sdk.stderr);
console.log(sdk.stdout.trim());
console.log('PASS typed surfaceColorAtElevation dynamic/zero/positive values, theme roles, ordered evaluation, official JVM/runtime parity, source-linked rejection and SDK compilation');
