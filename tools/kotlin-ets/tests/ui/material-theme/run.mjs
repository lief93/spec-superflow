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
const work = mkdtempSync(join(tmpdir(), 'kotlin-ets-material-theme-'));
const probe = process.env.KOTLIN_ETS_PROBE ?? '/tmp/kotlin-official-frontend-probe-06';
const cp = JSON.parse(readFileSync(join(probe, 'classpath.json'), 'utf8')).filter(existsSync);
const cpFile = join(work, 'classpath.txt');
writeFileSync(cpFile, cp.join('\n'));
console.log(`Evidence: ${work}`);
function run(label, command, args, status = 0) {
  const result = spawnSync(command, args, { encoding: 'utf8', timeout: 600000,
    env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' } });
  writeFileSync(join(work, `${label}.json`), JSON.stringify({ args, ...result }, null, 2));
  assert.equal(result.status, status, result.stdout + result.stderr);
  return result.stdout;
}
const output = join(work, 'Page.ets');
run('page', 'bash', [join(root, 'kotlin-ets'), '--entry', 'materialtheme.Page', '--classpath-file', cpFile,
  '--out', output, join(here, 'Page.kt')]);
const code = readFileSync(output, 'utf8');
assert.match(code, /WrappedBuilder<\[EtsMaterialContext\]>/);
assert.match(code, /content.builder\(__etsMaterialContext\)/);
assert.match(code, /Text\("Direct"\).*__etsTextStyleModifier\(__etsMaterialContext.contentColorFor\(__etsMaterialContext.colorScheme.primary\)/);
const classes = code.slice(code.indexOf('export class EtsMaterialColorValues'));
assert.ok(classes.startsWith('export class '));
const context = vm.createContext({ exports: {} });
vm.runInContext(ts.transpileModule(classes, { compilerOptions: { target: ts.ScriptTarget.ES2022,
  module: ts.ModuleKind.CommonJS } }).outputText, context);
// Obtain default constructor arguments from the emitted root call, not a duplicate palette.
const rootArgs = code.match(/this.Page\(new EtsMaterialContext\(new EtsMaterialColorValues\(([^)]*)\)/)?.[1];
assert.ok(rootArgs);
const args = JSON.parse(`[${rootArgs}]`);
const scheme = new context.exports.EtsMaterialColorValues(...args);
const roles = ['primary','secondary','tertiary','background','error','primaryContainer','secondaryContainer',
  'tertiaryContainer','errorContainer','inverseSurface','surface','surfaceVariant','surfaceBright',
  'surfaceContainer','surfaceContainerHigh','surfaceContainerHighest','surfaceContainerLow','surfaceContainerLowest'];
const ambient = new context.exports.EtsMaterialContext(scheme, 0xff00ffff);
const actual = [...roles.map(role => ambient.contentColorFor(scheme[role]) | 0), ambient.contentColorFor(0xff010203) | 0];
const collisionArgs = [...args];
collisionArgs[0] = collisionArgs[15] = 0xffff0000;
collisionArgs[1] = 0xff00ff00; collisionArgs[16] = 0xff0000ff;
const collision = new context.exports.EtsMaterialColorValues(...collisionArgs);
actual.push(new context.exports.EtsMaterialContext(collision, 0xff00ffff).contentColorFor(0xffff0000) | 0);
const jar = join(work, 'oracle.jar');
run('jvm-build', 'bash', [join(root, 'tests/stdlib/compiler.sh'), '-classpath', cp.join(':'), join(here, 'Oracle.kt'), '-d', jar]);
const expected = run('jvm', 'java', ['-cp', [jar, ...cp].join(':'), 'materialtheme.OracleKt']).trim().split('\n').map(Number);
assert.deepEqual(actual, expected);
writeFileSync(join(work, 'parity.json'), JSON.stringify({ actual, expected }, null, 2));
const buttonOutput = join(work, 'ThemedButton.ets');
run('ThemedButton', 'bash', [join(root, 'kotlin-ets'), '--entry', 'materialtheme.ThemedButton', '--classpath-file', cpFile,
  '--out', buttonOutput, join(here, 'Unsupported.kt')]);
assert.match(readFileSync(buttonOutput, 'utf8'), /\.disabledContentColor/);
const styledOutput = join(work, 'Styled.ets');
run('Styled', 'bash', [join(root, 'kotlin-ets'), '--entry', 'materialtheme.Styled', '--classpath-file', cpFile,
  '--out', styledOutput, join(here, 'Unsupported.kt')]);
assert.match(readFileSync(styledOutput, 'utf8'), /\.typography\.bodyLarge/);
for (const [entry, message] of [['ValueHelper', /composition invocation context/],
  ['ThemedCheckbox', /Theme-aware Checkbox/],
  ['ThemedSwitch', /Theme-aware Switch/], ['ThemedDivider', /Theme-aware Divider/],
  ['ThemedVerticalDivider', /Theme-aware Divider/], ['ExplicitSchemeLookup', /explicit receiver and Unspecified result semantics/]]) {
  const failedOutput = join(work, entry + '.ets');
  const log = run(entry, 'bash', [join(root, 'kotlin-ets'), '--entry', `materialtheme.${entry}`, '--classpath-file', cpFile,
    '--out', failedOutput, join(here, 'Unsupported.kt')], 2);
  assert.match(log, message); assert.equal(existsSync(failedOutput), false);
}
console.log('PASS theme/slot target flow, JVM content-color parity and explicit unsupported contracts');
