import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';

const result = ts.transpileModule(readFileSync(process.argv[2], 'utf8'), {
  compilerOptions: { target: ts.ScriptTarget.ES2022 }, reportDiagnostics: true,
});
assert.deepEqual(result.diagnostics, []);
// Capture matrix arguments, then independently apply them to known pixel values.
const context = vm.createContext({ ColorFilter: class { constructor(matrix) { this.matrix = matrix; } } });
vm.runInContext(result.outputText, context);
function tinted(color, pixel) {
  const matrix = context.__etsImageTint(color).matrix;
  assert.equal(matrix.length, 20);
  const rgba = Array.from({ length: 4 }, (_, row) => pixel.reduce((sum, value, column) =>
    sum + value / 255 * matrix[row * 5 + column], matrix[row * 5 + 4]));
  return rgba.map((value, i) => Math.round(value * (i < 3 ? rgba[3] : 1) * 255));
}
assert.deepEqual(tinted(0xffff0000, [30, 80, 100, 128]), [128, 0, 0, 128]);
assert.deepEqual(tinted(0x8000ff00, [50, 60, 70, 255]), [0, 128, 0, 128]);
assert.deepEqual(tinted(0xff0000ff, [255, 255, 255, 0]), [0, 0, 0, 0]);
assert.deepEqual(tinted(0xff0000ff, [1, 2, 3, 255]), [0, 0, 255, 255]);
console.log('PASS emitted SrcIn tint matrix preserves transparent/partial alpha and replaces RGB');
