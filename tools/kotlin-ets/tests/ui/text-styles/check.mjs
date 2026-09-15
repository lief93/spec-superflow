import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';

const [page, classpath] = process.argv.slice(2);
assert.ok(page && classpath, 'Pass generated Page.ets and fixture classpath.txt');
const here = dirname(fileURLToPath(import.meta.url));
const cp = readFileSync(classpath, 'utf8').trim().split('\n');
const jar = page + '.oracle.jar';
function run(command, args) {
  const result = spawnSync(command, args, { encoding: 'utf8', timeout: 120000 });
  assert.equal(result.status, 0, result.stdout + result.stderr);
  return result.stdout;
}
run('bash', [join(here, '../../stdlib/compiler.sh'), '-classpath', cp.join(':'),
  join(here, 'Styles.kt'), join(here, 'Oracle.kt'), '-d', jar]);
const oracle = run('java', ['-cp', [jar, ...cp].join(':'), 'fontfixtures.OracleKt']).trim().split('\n')
  .map(line => line.split(',').map(Number));
const generated = readFileSync(page, 'utf8');
// Execute only ordinary declarations from the actual output; ArkUI builders are SDK-tested separately.
const parsed = ts.createSourceFile('page.ts', generated.replace('export struct Page', 'export class Page'), ts.ScriptTarget.ES2022, true);
const ordinary = parsed.statements.filter(node => !ts.isImportDeclaration(node) &&
  !(ts.isClassDeclaration(node) && node.name?.text === 'Page')).map(node => node.getFullText(parsed)).join('\n');
const registrations = [];
const context = vm.createContext({ exports: {}, TextAlign: { Start: 0, Center: 1 }, TextOverflow: { Clip: 0 },
  FontStyle: { Normal: 0, Italic: 1 }, $rawfile: name => ({ name }),
  __etsFontApi: { registerFont: value => registrations.push(value) } });
vm.runInContext(ts.transpileModule(ordinary, { compilerOptions: { target: ts.ScriptTarget.ES2022,
  module: ts.ModuleKind.CommonJS } }).outputText, context);
const e = context.exports;
const style = e.heading(18, e.family());
assert.deepEqual([style.fontSize, style.fontWeight, style.lineHeight, style.color], oracle[0]);
assert.equal(registrations.length, 0, 'descriptors must not register native fonts');
const fonts = [[300, 0], [500, 0], [700, 0], [400, 1]].map(([weight, style]) => new e.EtsFont(String(weight), weight, style));
const actual = [];
for (const italic of [0, 1]) for (const weight of [100, 300, 350, 400, 450, 500, 550, 700, 900]) {
  const selected = e.__etsSelectFont(new e.EtsFontFamily(fonts), weight, italic);
  actual.push([selected.weight, selected.style]);
}
assert.deepEqual(actual, oracle.slice(1), 'font selection must match AndroidX FontMatcher');
const attrs = {};
const instance = new Proxy({}, { get: (_, name) => value => { attrs[name] = value; return instance; } });
const args = [null, null, null, null, null, null, null, null, 0, 2147483647, style, 0xff000000];
e.__etsTextStyleModifier(...args).applyNormalAttribute(instance);
assert.equal(attrs.fontSize, 18);
assert.equal(attrs.fontWeight, 500);
assert.equal(attrs.fontColor, 0xff156340);
assert.equal(attrs.lineHeight, 28);
assert.equal(attrs.textAlign, 1);
assert.equal(attrs.fontFamily, style.fontFamily.fonts[1].resource);
assert.equal(registrations.length, 1);
e.__etsTextStyleModifier(...args.map((v, i) => i === 0 ? 0xffff0000 : i === 1 ? 22 : i === 3 ? 400 : v)).applyNormalAttribute(instance);
assert.equal(attrs.fontSize, 22);
assert.equal(attrs.fontWeight, 400);
assert.equal(attrs.fontColor, 0xffff0000);
assert.equal(attrs.fontFamily, style.fontFamily.fonts[0].resource);
assert.equal(attrs.lineHeight, 28);
const empty = new e.EtsTextStyle(...Array(8).fill(null));
e.__etsTextStyleModifier(...args.map((v, i) => i === 10 ? empty : v)).applyNormalAttribute(instance);
assert.equal(attrs.lineHeight, 0, 'reset stale explicit line height');
assert.equal(attrs.fontFamily, 'HarmonyOS Sans', 'reset stale custom family');
assert.equal(attrs.fontSize, 14, 'explicit empty style is not omitted Material bodyLarge');
writeFileSync(page + '.parity.json', JSON.stringify({ oracle, actual, passed: true }, null, 2));
console.log('PASS JVM style values, 18 FontMatcher cases, native consumption precedence and reset');
