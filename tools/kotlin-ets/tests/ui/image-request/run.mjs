import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, writeFileSync, existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';

const here = dirname(fileURLToPath(import.meta.url)), root = resolve(here, '../../..');
const work = mkdtempSync(join(tmpdir(), 'kotlin-ets-image-request-'));
console.log(`Evidence: ${work}`);
const cp = process.argv[2];
assert.ok(cp && existsSync(cp), 'Supply a Compose/Coil 2 classpath file');
function compile(entry, mode, files, status = 0) {
  const out = join(work, entry + '.ets');
  const args = [join(root, 'kotlin-ets'), '--mode', mode, '--entry', 'requestfixtures.' + entry,
    '--classpath-file', cp, '--out', out, ...files.map(file => join(here, file))];
  const result = spawnSync('bash', args, { encoding: 'utf8', timeout: 600000,
    env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' } });
  writeFileSync(out + '.json', JSON.stringify({ args, ...result }, null, 2));
  assert.equal(result.status, status, result.stdout + result.stderr);
  assert.equal(existsSync(out), status === 0);
  return status === 0 ? readFileSync(out, 'utf8') : result.stdout;
}
const page = compile('Page', 'page', ['Values.kt', 'Page.kt']);
assert.match(page, /request\(url: string\)/);
assert.match(page, /configure\(new EtsImageRequestBuilder\(\), url, true\)/);
const values = compile('configure', 'language', ['Values.kt']);
const context = vm.createContext({ exports: {} });
vm.runInContext(ts.transpileModule(values, { compilerOptions: { target: ts.ScriptTarget.ES2022,
  module: ts.ModuleKind.CommonJS } }).outputText, context);
const api = context.exports;
const builder = new api.EtsImageRequestBuilder();
const first = api.configure(builder, 'https://example.com/a.svg', true);
assert.equal(first.requestData, 'https://example.com/a.svg');
assert.equal(first.crossfadeMillis, 100); // Coil 2.6 CrossfadeDrawable.DEFAULT_DURATION.
assert.ok(first.decoder instanceof api.EtsSvgDecoder);
const second = api.configure(builder, null, false);
assert.equal(second.requestData, null);
assert.equal(second.crossfadeMillis, 0);
assert.equal(first.requestData, 'https://example.com/a.svg');
assert.equal(first.crossfadeMillis, 100);
assert.notEqual(first, second);
assert.equal(builder.data('changed'), builder);
assert.equal(builder.crossfade(-1), builder);
assert.equal(builder.build().crossfadeMillis, 0);
assert.equal(builder.crossfade(230).build().crossfadeMillis, 230);
let calls = 0;
const observed = new api.EtsImageRequestBuilder();
const original = observed.data;
observed.data = function (value) { calls++; return original.call(this, value); };
api.configure(observed, 'x', true);
assert.equal(calls, 1);
const durationSource = compile('duration', 'language', ['Values.kt']);
const durationContext = vm.createContext({ exports: {} });
vm.runInContext(ts.transpileModule(durationSource, { compilerOptions: { target: ts.ScriptTarget.ES2022,
  module: ts.ModuleKind.CommonJS } }).outputText, durationContext);
const durationApi = durationContext.exports;
for (const millis of [-5, 0, 1, 230]) {
  assert.equal(durationApi.duration(new durationApi.EtsImageRequestBuilder(), millis).crossfadeMillis, Math.max(0, millis));
}
for (const [entry, message] of [['customContext', /direct LocalContext.current/],
  ['otherData', /supports string\/null/], ['otherDecoder', /default intrinsic-size/],
  ['otherOption', /Unsupported external call/]]) {
  assert.match(compile(entry, 'language', ['Unsupported.kt'], 2), message);
}
console.log('PASS request snapshots, builder identity, mutation, defaults, typed calls and explicit unsupported options');
