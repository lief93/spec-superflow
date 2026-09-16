import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, writeFileSync, existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';
const here = dirname(fileURLToPath(import.meta.url)), root = resolve(here, '../../..');
const work = mkdtempSync(join(tmpdir(), 'kotlin-ets-typography-'));
console.log('Evidence: ' + work);
const cp = JSON.parse(readFileSync('/tmp/kotlin-official-frontend-probe-06/classpath.json')).filter(existsSync);
const cpFile = join(work, 'classpath.txt');
writeFileSync(cpFile, cp.join('\n'));
function run(label, command, args) {
  const result = spawnSync(command, args, { encoding: 'utf8', timeout: 600000,
    env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' } });
  writeFileSync(join(work, label + '.json'), JSON.stringify({ args, ...result }, null, 2));
  assert.equal(result.status, 0, result.stdout + result.stderr);
  return result.stdout;
}
const model = join(work, 'Models.ets');
run('models', 'bash', [join(root, 'kotlin-ets'), '--mode', 'language', '--classpath-file', cpFile,
  '--out', model, join(here, 'Models.kt')]);
const context = vm.createContext({ exports: {} });
vm.runInContext(ts.transpileModule(readFileSync(model, 'utf8'), { compilerOptions: {
  target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS
} }).outputText, context);
const t = context.exports.defaults();
const roles = ['displayLarge','displayMedium','displaySmall','headlineLarge','headlineMedium','headlineSmall',
  'titleLarge','titleMedium','titleSmall','bodyLarge','bodyMedium','bodySmall','labelLarge','labelMedium','labelSmall'];
const actual = roles.flatMap(role => ['fontSize','lineHeight','fontWeight','letterSpacing'].map(field => t[role][field]));
actual.push(context.exports.selected(context.exports.customized()).fontSize);
const jar = join(work, 'oracle.jar');
run('jvm-build', 'bash', [join(root, 'tests/stdlib/compiler.sh'), '-classpath', cp.join(':'),
  join(here, 'Models.kt'), join(here, 'Oracle.kt'), '-d', jar]);
const expected = run('jvm', 'java', ['-cp', [jar, ...cp].join(':'), 'typography.OracleKt']).trim().split('\n').map(Number);
assert.deepEqual(actual, expected);
writeFileSync(join(work, 'parity.json'), JSON.stringify({ actual, expected }));
const out = join(work, 'Page.ets');
const typeOnly = join(work, 'TypeOnly.ets');
run('type-only', 'bash', [join(root, 'kotlin-ets'), '--mode', 'language', '--classpath-file', cpFile,
  '--out', typeOnly, join(here, 'TypeOnly.kt')]);
assert.match(readFileSync(typeOnly, 'utf8'), /export class EtsTypography/);
assert.match(readFileSync(typeOnly, 'utf8'), /export class EtsMaterialTheme/);
run('page', 'bash', [join(root, 'kotlin-ets'), '--entry', 'typography.Page', '--classpath-file', cpFile,
  '--out', out, join(here, 'Page.kt')]);
const code = readFileSync(out, 'utf8');
assert.match(code, /\.typography\.bodyLarge/);
assert.match(code, /\.typography\.labelLarge/);
assert.match(code, /\.typography\.titleSmall/);
assert.match(code, /typography: EtsTypography/);
assert.match(code, /__etsMaterialTheme/);
assert.doesNotMatch(code, /theme\.typography|theme\.colorScheme/);
const rendering = vm.createContext({ exports: {}, TextAlign: { Start: 0 }, TextDecorationType: { None: 0 } });
vm.runInContext(ts.transpileModule(code.slice(code.indexOf('export class EtsMaterialColorValues')), {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS }
}).outputText, rendering);
const api = rendering.exports;
const selected = context.exports.selected(context.exports.customized());
const modifier = api.__etsTextStyleModifier(null, 19, null, null, null, null, null, null, null, 0, 100, selected, 0xff000000);
assert.equal(modifier.fontSize, 19);
assert.equal(modifier.fontWeight, 700);
const inherited = api.__etsTextStyleModifier(null, null, null, null, null, null, null, null, null, 0, 100, t.bodyLarge, 0xff123456);
assert.equal(inherited.fontSize, 16);
assert.equal(inherited.lineHeight, 24);
assert.equal(inherited.color, 0xff123456);
console.log('PASS Typography JVM default/custom parity and nested theme/source slot generation');
