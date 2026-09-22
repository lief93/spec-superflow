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
const work = mkdtempSync(join(tmpdir(), 'kotlin-ets-surface-'));
const probe = process.env.KOTLIN_ETS_PROBE ?? '/tmp/kotlin-official-frontend-probe-06';
const cp = JSON.parse(readFileSync(join(probe, 'classpath.json'), 'utf8')).filter(existsSync);
const cpFile = join(work, 'classpath.txt');
writeFileSync(cpFile, cp.join('\n'));
console.log(`Evidence: ${work}`);
function compile(entry, source, expectedStatus = 0) {
  const output = join(work, `${entry}.ets`);
  const args = [join(root, 'kotlin-ets'), '--entry', `surface.${entry}`, '--classpath-file', cpFile,
    '--out', output, join(here, source)];
  const result = spawnSync('bash', args, { encoding: 'utf8', timeout: 600000,
    env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' } });
  writeFileSync(join(work, `${entry}.json`), JSON.stringify({ args, ...result }, null, 2));
  assert.equal(result.status, expectedStatus, result.stdout + result.stderr);
  assert.equal(existsSync(output), expectedStatus === 0);
  return expectedStatus === 0 ? readFileSync(output, 'utf8') : result.stdout + result.stderr;
}
const code = compile('Page', 'Page.kt');
assert.match(code, /EtsComposeSurface\(\{ content:/);
assert.match(code, /WithTheme\(\{ theme: \{ colors: \{ fontPrimary: 4294967295/);
assert.match(code, /Text\("Override"\)\.align\(Alignment.TopStart\)\.attributeModifier\(__etsTextStyleModifier\(4294901760,/);
assert.match(code, /fixedWidth: true, fixedHeight: true/);
assert.match(code, /\.clip\(true\)\.hitTestBehavior\(HitTestMode.Default\)\.width\(80(?:\.0)?\)\.height\(40(?:\.0)?\)/);
assert.match(code, /Text\("Outside"\)\.align\(Alignment.TopStart\)\.attributeModifier\(__etsTextStyleModifier\(4278190080,/);
assert.match(code, /Text\("Basic"\)\.fontColor\(4278190080\)\.fontSize\(14\)\.align\(Alignment.TopStart\)/);

// Execute the exact emitted layout callbacks, not a separate copy of their algorithm.
const start = code.indexOf('  onMeasureSize(');
const end = code.indexOf('  build()', start);
assert.ok(start >= 0 && end > start);
const context = vm.createContext({});
vm.runInContext(ts.transpileModule(`class Layout { ${code.slice(start, end)} }; globalThis.layout = new Layout();`,
  { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText, context);
const constraint = { minWidth: 80, minHeight: 40, maxWidth: 120, maxHeight: 70 };
const measured = [];
const children = [{ width: 100, height: 45 }, { width: 85, height: 60 }].map(result => ({
  measure(value) { measured.push(value); return result; }
}));
assert.deepEqual(JSON.parse(JSON.stringify(context.layout.onMeasureSize({}, children, constraint))), { width: 100, height: 60 });
assert.deepEqual(JSON.parse(JSON.stringify(measured)), [constraint, constraint]);
assert.deepEqual(JSON.parse(JSON.stringify(context.layout.onMeasureSize({}, [], constraint))), { width: 80, height: 40 });
context.layout.fixedWidth = true;
context.layout.fixedHeight = true;
assert.deepEqual(JSON.parse(JSON.stringify(context.layout.onMeasureSize({}, [], constraint))), { width: 120, height: 70 });
const positions = [];
context.layout.onPlaceChildren({}, [1, 2].map(() => ({ layout(value) { positions.push(value); } })), constraint);
assert.deepEqual(JSON.parse(JSON.stringify(positions)), [{ x: 0, y: 0 }, { x: 0, y: 0 }]);
for (const entry of ['DefaultBackground', 'DefaultContentColor']) {
  const defaults = compile(entry, 'Unsupported.kt');
  assert.match(defaults, /EtsMaterialContext/);
  assert.match(defaults, /__etsMaterialContext\.contentColor/);
}
for (const [entry, message] of [
  ['Elevated', /tonalElevation/], ['Interactive', /onClick/], ['Effectful', /requires a stable color value/],
  ['MutableColor', /requires a stable color value/]
]) assert.match(compile(entry, 'Unsupported.kt', 2), message);
compile('TouchPage', 'TouchPage.kt');
const snapshot = compile('SnapshotPage', 'SnapshotPage.kt');
assert.match(snapshot, /fontPrimary: color/);
assert.equal(snapshot.split('argb >>> 0').length - 1, 1, 'source val snapshots a mutable color once');
console.log('PASS explicit rectangular Surface, emitted layout callbacks, slots, and unsupported contracts');
