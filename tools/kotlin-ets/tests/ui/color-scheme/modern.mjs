import assert from 'node:assert/strict';
import { existsSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';

assert.ok(process.argv[2] && existsSync(process.argv[2]), 'Pass a Material3 48-role classpath.txt');
const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../../..');
const classpathFile = resolve(process.argv[2]);
const dependencies = readFileSync(classpathFile, 'utf8').split(/\r?\n/).filter(Boolean);
const work = mkdtempSync(join(tmpdir(), 'kotlin-ets-modern-color-scheme-'));
const source = join(here, 'ModernModels.kt');
const output = join(work, 'ModernModels.ets');
console.log(`Evidence: ${work}`);

function run(label, command, args) {
  const result = spawnSync(command, args, { encoding: 'utf8', timeout: 600000,
    env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' } });
  writeFileSync(join(work, `${label}.json`), JSON.stringify({ args, ...result }, null, 2));
  assert.equal(result.status, 0, result.stdout + result.stderr);
  return result.stdout;
}

run('language', 'bash', [join(root, 'kotlin-ets'), '--mode', 'language', '--classpath-file', classpathFile,
  '--out', output, source]);
const jar = join(work, 'oracle.jar');
run('jvm-build', 'bash', [join(root, 'tests/stdlib/compiler.sh'), '-classpath', dependencies.join(':'),
  source, join(here, 'ModernOracle.kt'), '-d', jar]);
const expected = run('jvm', 'java', ['-cp', [jar, ...dependencies].join(':'),
  'colorschememodern.ModernOracleKt']).trim().split('\n').map(Number);
const code = readFileSync(output, 'utf8');
assert.doesNotMatch(code, /ColorLightTokens|ColorDarkTokens|kotlin_ets_material_/);
const context = vm.createContext({ exports: {} });
vm.runInContext(ts.transpileModule(code, { compilerOptions: {
  target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS,
} }).outputText, context, { timeout: 2000 });
const actual = [...context.exports.modernLightDefaults(), ...context.exports.modernDarkDefaults(),
  ...context.exports.modernOverrides()];
assert.deepEqual(actual, expected);
assert.equal(actual.length, 32);
writeFileSync(join(work, 'parity.json'), JSON.stringify({ expected, actual }, null, 2));
console.log('PASS 48-role light/dark defaults, explicit fixed roles, dependent surfaceTint and source-order effects');
