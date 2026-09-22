import assert from 'node:assert/strict';
import {existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {dirname, join, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../../..');
const work = mkdtempSync(join(tmpdir(), 'kotlin-ets-color-copy-'));
const probe = process.env.KOTLIN_ETS_PROBE ?? '/tmp/kotlin-official-frontend-probe-06';
const classpath = JSON.parse(readFileSync(join(probe, 'classpath.json'), 'utf8')).filter(existsSync);
const dependencyManifest = existsSync(join(probe, 'compiler-dependencies.json')) ?
  join(probe, 'compiler-dependencies.json') :
  '/private/tmp/kotlin-official-frontend-probe-complete/compiler-dependencies.json';
const dependencies = JSON.parse(readFileSync(dependencyManifest, 'utf8')).map(item => item.path);
const classpathFile = join(work, 'classpath.txt');
writeFileSync(classpathFile, classpath.join('\n') + '\n');
console.log(`Evidence: ${work}`);

function compile(label, entry, source, expected = 0) {
  const output = join(work, `${label}.ets`);
  const args = [join(root, 'kotlin-ets'), '--mode', 'page', '--unsupported-policy', 'error',
    '--entry', entry, '--classpath-file', classpathFile, '--out', output, join(here, source)];
  const result = spawnSync('bash', args, {encoding: 'utf8', timeout: 600000,
    env: {...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC'}});
  writeFileSync(join(work, `${label}.json`), JSON.stringify({args, status: result.status,
    stdout: result.stdout, stderr: result.stderr}, null, 2));
  assert.equal(result.status, expected, result.stdout + result.stderr);
  assert.equal(existsSync(output), expected === 0);
  return expected === 0 ? readFileSync(output, 'utf8') : JSON.parse(result.stdout.trim().split('\n').at(-1));
}

const code = compile('page', 'colorcopy.Page', 'Page.kt');
assert.match(code, /import \{ ColorMetrics \} from "@ohos\.arkui\.node";/);
assert.match(code, /ColorMetrics\.numeric\(color\)/);
assert.match(code, /ColorMetrics\.rgba\(outputRed, outputGreen, outputBlue, outputAlpha \/ 255\)/);
assert.match(code, /__etsCopyColor\(color, alpha, null, null, null\)/);
assert.match(code, /__etsCopyColor\(color, alpha, red, green, blue\)/);
assert.match(code, /__etsCopyColor\(color, null, null, null, null\)/);

const parsed = ts.createSourceFile('page.ts', code.replace('export struct Page', 'export class Page'),
  ts.ScriptTarget.ES2022, true);
const ordinary = parsed.statements.filter(node => !ts.isImportDeclaration(node) &&
  !(ts.isClassDeclaration(node) && node.name?.text === 'Page')).map(node => node.getFullText(parsed)).join('\n');
const transpiled = ts.transpileModule(ordinary, {compilerOptions: {
  target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS,
}});
assert.deepEqual(transpiled.diagnostics ?? [], []);
let numericCalls = 0;
let rgbaCalls = 0;
const metrics = value => ({alpha: Math.floor(value / 0x1000000) % 0x100,
  red: Math.floor(value / 0x10000) % 0x100, green: Math.floor(value / 0x100) % 0x100,
  blue: value % 0x100});
const ColorMetrics = {
  numeric(value) { numericCalls++; return metrics(value); },
  rgba(red, green, blue, alpha = 1) { rgbaCalls++; return {red, green, blue, alpha: Math.floor(alpha * 255 + 0.5)}; },
};
const context = vm.createContext({exports: {}, ColorMetrics});
vm.runInContext(transpiled.outputText, context);
const base = 0x80402010;
const generated = [context.exports.unchanged(base), context.exports.alphaOnly(base, 0.25),
  context.exports.reordered(base, 0.1, 0.2, 0.3, 0.25),
  context.exports.reordered(base, -1, 2, Number.NaN, 1.5), context.exports.reorderedEffects(base)]
  .map(value => value.toString(16).padStart(8, '0'));
assert.equal(numericCalls, 5);
assert.equal(rgbaCalls, 5);

const classes = join(work, 'oracle-classes');
mkdirSync(classes);
const java = process.env.JAVA_HOME ? join(process.env.JAVA_HOME, 'bin/java') :
  '/Applications/Android Studio.app/Contents/jbr/Contents/Home/bin/java';
const oracleCompile = spawnSync(java, ['-cp', dependencies.join(':'),
  'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler', '-no-stdlib', '-no-reflect',
  '-classpath', classpath.join(':'), '-d', classes, join(here, 'Oracle.kt')],
{encoding: 'utf8', timeout: 600000});
writeFileSync(join(work, 'oracle-compile.json'), JSON.stringify({status: oracleCompile.status,
  stdout: oracleCompile.stdout, stderr: oracleCompile.stderr}, null, 2));
assert.equal(oracleCompile.status, 0, oracleCompile.stdout + oracleCompile.stderr);
const oracle = spawnSync(java, ['-cp', `${classes}:${classpath.join(':')}`, 'colorcopy.OracleKt'],
  {encoding: 'utf8', timeout: 600000});
writeFileSync(join(work, 'oracle.json'), JSON.stringify({status: oracle.status,
  stdout: oracle.stdout, stderr: oracle.stderr}, null, 2));
assert.equal(oracle.status, 0, oracle.stdout + oracle.stderr);
assert.deepEqual(generated, oracle.stdout.trim().split('\n'),
  'generated runtime channel behavior must match the official Compose JVM implementation');

const unsupported = compile('unsupported', 'colorcopy.unsupported.Page', 'Unsupported.kt', 2);
assert.equal(unsupported.code, 'UNSUPPORTED');
assert.match(unsupported.message, /Unsupported external call: androidx\.compose\.ui\.graphics\.Color$/);
assert.equal(resolve(unsupported.source.file), resolve(join(here, 'Unsupported.kt')));
assert.equal(unsupported.source.line, 10);
assert.equal(unsupported.source.column, 16);

const sdk = spawnSync(process.execPath, [join(here, '../basic-controls-sdk.mjs'), join(work, 'page.ets')], {
  encoding: 'utf8', timeout: 600000,
  env: {...process.env, KOTLIN_ETS_SDK_SEED:
    process.env.KOTLIN_ETS_SDK_SEED ?? '/private/tmp/kotlin-ets-basic-controls-sdk-bZjYXV/harmony'},
});
writeFileSync(join(work, 'sdk.json'), JSON.stringify({status: sdk.status, stdout: sdk.stdout, stderr: sdk.stderr}, null, 2));
assert.equal(sdk.status, 0, sdk.stdout + sdk.stderr);
console.log(sdk.stdout.trim());
console.log('PASS typed Color.copy defaults, named/runtime channels, native ColorMetrics and source-linked wide-gamut rejection');
