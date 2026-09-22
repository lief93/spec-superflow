import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, writeFileSync, existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../../..');
const work = mkdtempSync(join(tmpdir(), 'kotlin-ets-dimensions-'));
const cp = JSON.parse(readFileSync('/tmp/kotlin-official-frontend-probe-06/classpath.json', 'utf8')).filter(existsSync);
writeFileSync(join(work, 'classpath.txt'), cp.join('\n'));
console.log(`Evidence: ${work}`);
function compile(entry, expected = 0, mode = 'page', file = mode === 'page' ? 'Page.kt' : 'Values.kt') {
  const output = join(work, entry + '.ets');
  const args = [join(root, 'kotlin-ets'), '--mode', mode, '--classpath-file', join(work, 'classpath.txt'),
    ...(mode === 'page' ? ['--entry', `dimensions.${entry}`] : []), '--out', output,
    join(here, file)];
  const result = spawnSync('bash', args, { encoding: 'utf8', timeout: 600000,
    env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' } });
  writeFileSync(join(work, entry + '.json'), JSON.stringify({ args, ...result }, null, 2));
  assert.equal(result.status, expected, result.stdout + result.stderr);
  assert.equal(existsSync(output), expected === 0);
  return expected === 0 ? readFileSync(output, 'utf8') : result.stdout;
}
const page = compile('Page');
assert.match(page, /Content\(width: number \| null, fontSize: number\)/);
assert.match(page, /Compose dimension consumer received Dp\.Unspecified/);
assert.match(page, /\)\(width\)\)/);
assert.doesNotMatch(page, /layoutPx|migrationContext/);
assert.match(compile('Em', 2), /Unsupported dimension value: androidx.compose.ui.unit.em/);
assert.match(compile('Unspecified', 2), /Compose dimension consumer requires a specified Dp value/);
assert.match(compile('Zero'), /\.width\(0(?:\.0)?\)/);
assert.doesNotMatch(compile('Constraints'), /constraintSize/);
const values = compile('Values', 0, 'language');
assert.match(values, /value: number \| null = null/);
assert.match(values, /value: number \| null = null, fallback: number \| null = 0/);
assert.match(values, /value === null/);
const jar = join(work, 'oracle.jar');
const build = spawnSync('bash', [join(root, 'tests/stdlib/compiler.sh'), '-classpath', cp.join(':'),
  join(here, 'Values.kt'), join(here, 'Oracle.kt'), '-d', jar], { encoding: 'utf8', timeout: 120000 });
writeFileSync(join(work, 'jvm-build.json'), JSON.stringify(build, null, 2));
assert.equal(build.status, 0, build.stderr);
const oracle = spawnSync('java', ['-cp', [jar, ...cp].join(':'), 'dimensionvalues.OracleKt'], { encoding: 'utf8' });
assert.equal(oracle.status, 0, oracle.stderr);
const expected = oracle.stdout.trim().split('\n').map(Number);
const context = vm.createContext({ exports: {} });
vm.runInContext(ts.transpileModule(values, { compilerOptions: {
  target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS
} }).outputText, context);
const actual = Array.from(context.exports.observations());
assert.deepEqual(actual, expected);
writeFileSync(join(work, 'parity.json'), JSON.stringify({ expected, actual }, null, 2));
assert.throws(() => context.exports.consumeUnspecified(), /Dp\.value received Dp\.Unspecified/);
assert.equal(context.exports.currentDimensionReads(), 1, 'dynamic unspecified Dp must be evaluated once');
for (const entry of ['RepeatedPadding', 'BoundPadding']) {
  const generated = compile(entry, 0, 'page', 'Padding.kt');
  const parsed = ts.createSourceFile('padding.ts', generated.replace(`export struct ${entry}`, `export class ${entry}`)
    .replace(/Stack\((\{[^}]*\})\) \{\}/g, 'Stack($1)'), ts.ScriptTarget.ES2022, true);
  const component = parsed.statements.find(node => ts.isClassDeclaration(node) && node.name?.text === entry);
  assert.ok(component);
  const ordinary = parsed.statements.filter(node => node !== component).map(node => node.getFullText(parsed)).join('\n');
  const executable = ordinary + `\nexport class ${entry} {\n` + component.members
    .filter(node => node.name?.getText(parsed) !== 'build').map(node => node.getFullText(parsed)).join('\n') + '\n}';
  const pads = [];
  const vmContext = vm.createContext({ exports: {}, Builder() {}, Alignment: { TopStart: 0 },
    Stack() { return { padding(value) { pads.push(value); } }; } });
  vm.runInContext(ts.transpileModule(executable, { compilerOptions: {
    target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS
  } }).outputText, vmContext);
  vm.runInContext(`new exports.${entry}().${entry}()`, vmContext);
  assert.equal(vmContext.exports.paddingReads, 1, 'source padding argument must execute once');
  assert.deepEqual(JSON.parse(JSON.stringify(pads)), [{ left: 1, right: 1, top: 0, bottom: 0 }]);
}
const sdk = spawnSync(process.execPath, [join(here, '../basic-controls-sdk.mjs'), join(work, 'Page.ets')], {
  encoding: 'utf8', timeout: 600000,
  env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC',
    KOTLIN_ETS_SDK_SEED: process.env.KOTLIN_ETS_SDK_SEED ?? '/private/tmp/kotlin-ets-basic-controls-sdk-bZjYXV/harmony' },
});
assert.equal(sdk.status, 0, sdk.stdout + sdk.stderr);
process.stdout.write(sdk.stdout);
console.log('PASS optional Dp defaults, conditions, equality, concrete guards, ordered effects, JVM parity and SDK');
