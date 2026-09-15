import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, writeFileSync, mkdirSync, cpSync, existsSync, readdirSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';

const here = dirname(fileURLToPath(import.meta.url)), root = resolve(here, '../../..');
const work = mkdtempSync(join(tmpdir(), 'kotlin-ets-font-values-'));
console.log(`Evidence: ${work}`);
const cp = JSON.parse(readFileSync('/tmp/kotlin-official-frontend-probe-06/classpath.json', 'utf8')).filter(existsSync);
function run(name, cmd, args, status = 0) {
  const result = spawnSync(cmd, args, { encoding: 'utf8', timeout: 600000,
    env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' } });
  writeFileSync(join(work, name + '.json'), JSON.stringify({ args, ...result }, null, 2));
  assert.equal(result.status, status, result.stdout + result.stderr);
  return result.stdout;
}
const classes = join(work, 'classes');
mkdirSync(classes);
run('resource-class', 'javac', ['-d', classes, join(here, 'R.java')]);
cp.unshift(classes);
writeFileSync(join(work, 'classpath.txt'), cp.join('\n'));
const font = process.env.KOTLIN_ETS_TEST_FONT ?? '/System/Library/Fonts/Supplemental/Arial.ttf';
const res = join(work, 'res');
mkdirSync(join(res, 'font'), { recursive: true });
for (const name of ['normal', 'medium', 'unused']) cpSync(font, join(res, 'font', name + '.ttf'));
const pack = join(work, 'pack');
run('resources', 'python3', [join(root, 'font-resources.py'), '--res-dir', res, '--namespace', 'fontfixtures', '--out', pack]);
function compile(name, mode = 'language', status = 0, input = name + '.kt') {
  const out = join(work, name + '.ets');
  const stdout = run(name, 'bash', [join(root, 'kotlin-ets'), '--mode', mode,
    ...(mode === 'page' ? ['--entry', 'fontfixtures.Page'] : []), '--classpath-file', join(work, 'classpath.txt'),
    '--font-resources', join(pack, 'fonts.properties'), '--out', out, join(here, input),
    ...(mode === 'page' ? [join(here, 'Values.kt')] : [])], status);
  assert.equal(existsSync(out), status === 0);
  assert.equal(existsSync(out + '.resources'), status === 0);
  return status === 0 ? readFileSync(out, 'utf8') : JSON.parse(stdout.trim().split('\n').at(-1));
}
const values = compile('Values');
const jar = join(work, 'oracle.jar');
run('oracle-build', 'bash', [join(root, 'tests/stdlib/compiler.sh'), '-classpath', cp.join(':'),
  join(here, 'Values.kt'), join(here, 'Oracle.kt'), '-d', jar]);
const expected = run('oracle', 'java', ['-cp', [jar, ...cp].join(':'), 'fontfixtures.OracleKt']).trim().split('\n').map(Number);
const context = vm.createContext({ exports: {} });
vm.runInContext(ts.transpileModule(values, { compilerOptions: {
  target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS
} }).outputText, context);
const actual = Array.from(context.exports.observations());
assert.deepEqual(actual, expected);
assert.deepEqual(actual, [400, 500, 450, 1]);
assert.match(values, /same\(value: EtsFontFamily\): EtsFontFamily/);
const artifacts = readdirSync(join(work, 'Values.ets.resources/rawfile'));
assert.equal(artifacts.length, 2, 'unused font must not be emitted');
for (const artifact of artifacts) assert.deepEqual(readFileSync(join(work, 'Values.ets.resources/rawfile', artifact)), readFileSync(font));
compile('Page', 'page');
assert.match(compile('Missing', 'language', 2).message, /Unmapped font resource/);
assert.match(compile('Empty', 'language', 2).message, /requires nonempty/);
writeFileSync(join(work, 'parity.json'), JSON.stringify({ expected, actual }, null, 2));
console.log('PASS JVM font descriptor parity, once-only construction and referenced resource bytes; native font application pending');
