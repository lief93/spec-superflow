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
const work = mkdtempSync(join(tmpdir(), 'kotlin-ets-color-scheme-'));
const probe = process.env.KOTLIN_ETS_PROBE ?? '/tmp/kotlin-official-frontend-probe-06';
const cp = JSON.parse(readFileSync(join(probe, 'classpath.json'), 'utf8')).filter(existsSync);
const cpFile = join(work, 'classpath.txt');
writeFileSync(cpFile, cp.join('\n'));
console.log(`Evidence: ${work}`);
function run(label, command, args) {
  const result = spawnSync(command, args, { encoding: 'utf8', timeout: 600000,
    env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' } });
  writeFileSync(join(work, `${label}.json`), JSON.stringify({ args, ...result }, null, 2));
  assert.equal(result.status, 0, result.stdout + result.stderr);
  return result.stdout;
}
const output = join(work, 'Models.ets');
run('language', 'bash', [join(root, 'kotlin-ets'), '--mode', 'language', '--classpath-file', cpFile,
  '--out', output, join(here, 'Models.kt')]);
const jar = join(work, 'oracle.jar');
run('jvm-build', 'bash', [join(root, 'tests/stdlib/compiler.sh'), '-classpath', cp.join(':'),
  join(here, 'Models.kt'), join(here, 'Oracle.kt'), '-d', jar]);
const expected = run('jvm', 'java', ['-cp', [jar, ...cp].join(':'), 'colorscheme.OracleKt']).trim().split('\n').map(Number);
const context = vm.createContext({ exports: {} });
vm.runInContext(ts.transpileModule(readFileSync(output, 'utf8'), { compilerOptions: {
  target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS
} }).outputText, context, { timeout: 2000 });
const actual = [...context.exports.roles(context.exports.scheme(false)),
  ...context.exports.roles(context.exports.scheme(true)), ...context.exports.overrides(), ...context.exports.callForms()];
assert.deepEqual(actual, expected);
assert.equal(actual.length, 86);
writeFileSync(join(work, 'parity.json'), JSON.stringify({ expected, actual }, null, 2));
run('page', 'bash', [join(root, 'kotlin-ets'), '--entry', 'colorscheme.Page', '--classpath-file', cpFile,
  '--out', join(work, 'Page.ets'), join(here, 'Models.kt'), join(here, 'Page.kt')]);
assert.match(readFileSync(join(work, 'Page.ets'), 'utf8'), /\.fontColor\(colors.primary\)/);
run('modules', 'bash', [join(root, 'kotlin-ets'), '--mode', 'language', '--classpath-file', cpFile,
  '--out-dir', join(work, 'modules'), join(here, 'Models.kt'), join(here, 'Consumer.kt')]);
for (const name of ['Models', 'Consumer']) {
  const code = readFileSync(join(work, `modules/${name}.ets`), 'utf8');
  assert.match(code, /import \{ EtsMaterialColorScheme \} from ['"]\.\/EtsMaterialColorScheme['"]/);
  assert.doesNotMatch(code, /class EtsMaterialColorScheme/);
}
assert.match(readFileSync(join(work, 'modules/EtsMaterialColorScheme.ets'), 'utf8'), /export interface EtsMaterialColorScheme/);
console.log('PASS light/dark semantic defaults, named/positional/mixed calls, ordered effects, parameter/property flow and type-only module support');
