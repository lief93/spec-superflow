import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, writeFileSync, existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';

const here = dirname(fileURLToPath(import.meta.url)), root = resolve(here, '../../..');
const work = mkdtempSync(join(tmpdir(), 'kotlin-ets-empty-modifier-'));
console.log(`Evidence: ${work}`);
const cp = JSON.parse(readFileSync('/tmp/kotlin-official-frontend-probe-06/classpath.json', 'utf8')).filter(existsSync);
writeFileSync(join(work, 'classpath.txt'), cp.join('\n'));
function compile(entry, status) {
  const out = join(work, entry + '.ets');
  const args = [join(root, 'kotlin-ets'), '--mode', 'page', '--entry', 'emptymodifier.' + entry,
    '--classpath-file', join(work, 'classpath.txt'), '--out', out, join(here, 'Page.kt'), join(here, 'Child.kt'), join(here, 'BadDefault.kt')];
  const result = spawnSync('bash', args, { encoding: 'utf8', timeout: 600000,
    env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' } });
  writeFileSync(out + '.json', JSON.stringify({ args, ...result }, null, 2));
  assert.equal(result.status, status, result.stdout + result.stderr);
  assert.equal(existsSync(out), status === 0);
  return status === 0 ? readFileSync(out, 'utf8') : result.stdout;
}
const page = compile('Page', 0);
assert.match(page, /Child\(modifier: EtsEmptyModifier/);
assert.match(page, /Child\(__etsEmptyModifier\)/);
assert.match(page, /Child\(same\(__etsEmptyModifier\)\)/);
assert.match(page, /padding\(/);
const parsed = ts.createSourceFile('page.ts', page.replace('export struct Page', 'export class Page'), ts.ScriptTarget.ES2022, true);
const ordinary = parsed.statements.filter(node => !(ts.isClassDeclaration(node) && node.name?.text === 'Page') &&
  !(ts.isFunctionDeclaration(node) && node.name?.text === 'Child')).map(node => node.getFullText(parsed)).join('\n');
assert.ok(ordinary.includes('export class EtsEmptyModifier'));
const context = vm.createContext({ exports: {} });
vm.runInContext(ts.transpileModule(ordinary, { compilerOptions: {
  target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS
} }).outputText, context);
const e = context.exports;
assert.equal(e.same(e.__etsEmptyModifier), e.__etsEmptyModifier);
assert.equal(e.same(e.__etsEmptyModifier), e.__etsEmptyModifier);
assert.equal(e.reads, 2, 'helper effects execute once per call');
const nonempty = compile('Nonempty', 0);
assert.match(nonempty, /Child_Modifier1\(/);
assert.match(nonempty, /padding\(8(?:\.0)?\)/);
assert.match(nonempty, /padding\(16(?:\.0)?\)/);
const badDefault = JSON.parse(compile('DefaultFailure', 2).trim().split('\n').at(-1));
assert.match(badDefault.message, /Unsupported TextAlign value: Left/);
assert.equal(resolve(badDefault.source.file), join(here, 'BadDefault.kt'));
assert.equal(badDefault.source.line, 6);
console.log('PASS empty Modifier identity, helper effects, static chain specialization and source diagnostics');
