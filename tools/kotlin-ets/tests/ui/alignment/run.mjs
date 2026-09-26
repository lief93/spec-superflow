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
const work = mkdtempSync(join(tmpdir(), 'kotlin-ets-alignment-'));
const probe = process.env.KOTLIN_ETS_PROBE ?? '/tmp/kotlin-official-frontend-probe-06';
const cp = JSON.parse(readFileSync(join(probe, 'classpath.json'), 'utf8')).filter(existsSync);
const cpFile = join(work, 'classpath.txt');
writeFileSync(cpFile, cp.join('\n'));
console.log(`Evidence: ${work}`);
function compile(entry, file, status = 0) {
  const output = join(work, entry + '.ets');
  const args = [join(root, 'kotlin-ets'), '--entry', `alignment.${entry}`, '--classpath-file', cpFile,
    '--out', output, join(here, file)];
  const result = spawnSync('bash', args, { encoding: 'utf8', timeout: 600000,
    env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' } });
  writeFileSync(join(work, entry + '.json'), JSON.stringify({ args, ...result }, null, 2));
  assert.equal(result.status, status, result.stdout + result.stderr);
  assert.equal(existsSync(output), status === 0);
  return status === 0 ? readFileSync(output, 'utf8') : result.stdout;
}
const code = compile('Page', 'Page.kt');
assert.match(code, /Sample\(name: string, alignment: Alignment\)/);
assert.match(code, /Stack\(\{ alignContent: alignment \}\)/);
assert.match(code, /\.alignItems\(horizontal\(true\)\)/);
assert.match(code, /\.alignItems\(vertical\(true\)\)/);
assert.doesNotMatch(code, /__etsMaterialContext/);
const context = vm.createContext({ exports: {}, HorizontalAlign: { Center: 1, End: 2 },
  VerticalAlign: { Center: 3, Bottom: 4 }, Alignment: { BottomEnd: 5, TopStart: 6 } });
const functions = code.slice(0, code.indexOf('@Builder'));
assert.ok(functions.includes('export function corner'));
vm.runInContext(ts.transpileModule(functions, { compilerOptions: { target: ts.ScriptTarget.ES2022,
  module: ts.ModuleKind.CommonJS } }).outputText, context);
assert.deepEqual([context.exports.horizontal(true), context.exports.horizontal(false),
  context.exports.vertical(true), context.exports.vertical(false), context.exports.corner(true), context.exports.corner(false)], [1,2,3,4,5,6]);
assert.match(compile('Custom', 'Unsupported.kt', 2), /BiasAlignment/);
for (const [entry, alignment] of [
  ['ColumnOrder', 'afterWidth'],
  ['RowOrder', 'afterWidthVertical'],
  ['BoxOrder', 'afterWidthBox'],
]) {
  const ordered = compile(entry, 'Order.kt');
  const widthEvaluation = ordered.indexOf('[Math.fround(nextWidth())]');
  const alignmentEvaluation = ordered.indexOf(`[${alignment}()]`);
  assert.ok(widthEvaluation >= 0 && alignmentEvaluation > widthEvaluation,
    `${entry} evaluates source arguments from left to right`);
  assert.equal((ordered.match(/nextWidth\(\)/g) ?? []).length, 2,
    `${entry} width declaration plus one invocation`);
  assert.equal((ordered.match(new RegExp(`${alignment}\\(\\)`, 'g')) ?? []).length, 2,
    `${entry} alignment declaration plus one invocation`);
  assert.match(ordered, /\.width\(__etsUiArg\d+_\d+\)/);
  if (entry === 'BoxOrder') assert.match(ordered, /Stack\(\{ alignContent: __etsUiArg\d+_\d+ \}\)/);
  else assert.match(ordered, /\.alignItems\(__etsUiArg\d+_\d+\)/);
}
const bound = compile('BoundOrder', 'Order.kt');
assert.match(bound, /\.alignItems\(alignment\)/);
assert.match(bound, /\.width\(Math\.fround\(width\)\)/);
assert.equal((bound.match(/nextWidth\(\)/g) ?? []).length, 2, 'declaration plus one invocation');
assert.equal((bound.match(/afterWidth\(\)/g) ?? []).length, 2, 'declaration plus one invocation');
console.log('PASS typed alignment, automatic source-order binding and explicit custom-alignment rejection');
