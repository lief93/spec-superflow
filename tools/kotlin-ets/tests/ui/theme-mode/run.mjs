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
const work = mkdtempSync(join(tmpdir(), 'kotlin-ets-theme-mode-'));
const probe = process.env.KOTLIN_ETS_PROBE ?? '/tmp/kotlin-official-frontend-probe-06';
const classpath = JSON.parse(readFileSync(join(probe, 'classpath.json'), 'utf8')).filter(existsSync);
const classpathFile = join(work, 'classpath.txt');
const output = join(work, 'Page.ets');
writeFileSync(classpathFile, classpath.join('\n') + '\n');
console.log(`Evidence: ${work}`);

const args = [join(root, 'kotlin-ets'), '--mode', 'page', '--unsupported-policy', 'error',
  '--entry', 'thememode.Page', '--classpath-file', classpathFile, '--out', output, join(here, 'Page.kt')];
const compile = spawnSync('bash', args, {encoding: 'utf8', timeout: 600000,
  env: {...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC'}});
writeFileSync(join(work, 'compile.json'), JSON.stringify({args, status: compile.status,
  stdout: compile.stdout, stderr: compile.stderr}, null, 2));
assert.equal(compile.status, 0, compile.stdout + compile.stderr);

const code = readFileSync(output, 'utf8');
assert.match(code, /import __etsResourceManager from "@ohos\.resourceManager";/);
assert.match(code, /if \(__etsIsSystemInDarkTheme\(\)\)/);
assert.match(code, /getContext\(\)\.resourceManager\.getConfigurationSync\(\)\.colorMode === __etsResourceManager\.ColorMode\.DARK/);
assert.doesNotMatch(code, /if \((?:true|false)\)/, 'theme mode must remain a runtime read');

const parsed = ts.createSourceFile('page.ts', code.replace('export struct Page', 'export class Page'),
  ts.ScriptTarget.ES2022, true);
const ordinary = parsed.statements.filter(node => !ts.isImportDeclaration(node) &&
  !(ts.isClassDeclaration(node) && node.name?.text === 'Page')).map(node => node.getFullText(parsed)).join('\n');
const transpiled = ts.transpileModule(ordinary, {compilerOptions: {
  target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS,
}});
assert.deepEqual(transpiled.diagnostics ?? [], []);
let colorMode = 1;
let reads = 0;
const context = vm.createContext({exports: {}, getContext: () => ({resourceManager: {
  getConfigurationSync() { reads++; return {colorMode}; },
}}), __etsResourceManager: {ColorMode: {DARK: 0, LIGHT: 1}}});
vm.runInContext(transpiled.outputText, context);
assert.equal(context.exports.__etsIsSystemInDarkTheme(), false);
colorMode = 0;
assert.equal(context.exports.__etsIsSystemInDarkTheme(), true);
colorMode = 1;
assert.equal(context.exports.__etsIsSystemInDarkTheme(), false);
assert.equal(reads, 3, 'every call must read the current configuration');

const sdk = spawnSync(process.execPath, [join(here, '../basic-controls-sdk.mjs'), output], {
  encoding: 'utf8', timeout: 600000,
  env: {...process.env, KOTLIN_ETS_SDK_SEED:
    process.env.KOTLIN_ETS_SDK_SEED ?? '/private/tmp/kotlin-ets-basic-controls-sdk-bZjYXV/harmony'},
});
writeFileSync(join(work, 'sdk.json'), JSON.stringify({status: sdk.status, stdout: sdk.stdout, stderr: sdk.stderr}, null, 2));
assert.equal(sdk.status, 0, sdk.stdout + sdk.stderr);
console.log(sdk.stdout.trim());
console.log('PASS runtime Harmony configuration drives typed Compose theme mode reads without caching');
