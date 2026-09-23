import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, writeFileSync, existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';

const here = dirname(fileURLToPath(import.meta.url)), root = resolve(here, '../../..');
const work = mkdtempSync(join(tmpdir(), 'kotlin-ets-layout-weight-'));
console.log(`Evidence: ${work}`);
const cp = JSON.parse(readFileSync('/tmp/kotlin-official-frontend-probe-06/classpath.json', 'utf8')).filter(existsSync);
writeFileSync(join(work, 'classpath.txt'), cp.join('\n'));
function compile(entry, status = 0) {
  const out = join(work, entry + '.ets');
  const args = [join(root, 'kotlin-ets'), '--mode', 'page', '--entry', 'weightfixtures.' + entry,
    '--classpath-file', join(work, 'classpath.txt'), '--out', out, join(here, 'Page.kt')];
  const result = spawnSync('bash', args, { encoding: 'utf8', timeout: 600000,
    env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' } });
  writeFileSync(out + '.json', JSON.stringify({ args, ...result }, null, 2));
  assert.equal(result.status, status, result.stdout + result.stderr);
  assert.equal(existsSync(out), status === 0);
  return status === 0 ? readFileSync(out, 'utf8') : result.stdout;
}
assert.match(compile('UnknownSlotParent', 2), /weight requires a known Row or Column parent/);
const page = compile('Page');
assert.match(page, /Page\(first: number = 1/);
assert.equal((page.match(/\.layoutWeight\(/g) ?? []).length, 4);
assert.match(page, /\.padding\(8\.0\)\.layoutWeight\(__etsLayoutWeight\(first\)\)/);
assert.doesNotMatch(page, /\.(?:width|height)\("100%"\)\.layoutWeight\(/);
const parsed = ts.createSourceFile('page.ts', page.replace('export struct Page', 'export class Page'), ts.ScriptTarget.ES2022, true);
const ordinary = parsed.statements.filter(node => !(ts.isClassDeclaration(node) && node.name?.text === 'Page'))
  .map(node => node.getFullText(parsed)).join('\n');
const context = vm.createContext({ exports: {} });
vm.runInContext(ts.transpileModule(ordinary, { compilerOptions: { target: ts.ScriptTarget.ES2022,
  module: ts.ModuleKind.CommonJS } }).outputText, context);
const normalize = context.exports.__etsLayoutWeight;
assert.equal(normalize(1.5), 1.5);
assert.equal(normalize(Infinity), 3.4028234663852886e38);
for (const weight of [0, -1, NaN]) assert.throws(() => normalize(weight), { name: 'IllegalArgumentException' });
assert.match(compile('NoFill', 2), /fill=true/);
assert.match(compile('Zero', 2), /weight must be positive/);
assert.match(compile('Repeated', 2), /Repeated weight/);
console.log('PASS typed weight, immutable parameters, parent-data hoisting and rejection; native bounds checked separately');
