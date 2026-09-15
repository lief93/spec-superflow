import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { join } from 'node:path';

assert.ok(process.argv[2], 'Pass native dumpLayout -a JSON');
let screenshot;
if (process.argv[3]) {
  const modules = process.env.KOTLIN_ETS_NODE_MODULES ?? join(process.env.HOME,
    '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules');
  const { PNG } = createRequire(import.meta.url)(join(modules, 'pngjs'));
  screenshot = PNG.sync.read(readFileSync(process.argv[3]));
}
const nodes = [];
function visit(node) { nodes.push(node); (node.children ?? []).forEach(visit); }
visit(JSON.parse(readFileSync(process.argv[2], 'utf8')));
const expected = { Outer: '#FF00FF00', Forwarded: '#FFFFFF00', Explicit: '#FF0000FF',
  Restored: '#FF00FF00', Fallback: '#FF00FFFF', Inherited: '#FF00FF00', Direct: '#FF00FF00' };
for (const [text, color] of Object.entries(expected)) {
  const matches = nodes.filter(node => node.attributes.text === text);
  assert.equal(matches.length, 1, text);
  const font = matches[0].extraAttrs?.FontColor;
  if (font) assert.ok(font.startsWith(color), `${text}: ${font}`);
  else {
    assert.ok(screenshot, `${text}: missing inspector font data; supply same-run native PNG`);
    const [left, top, right, bottom] = matches[0].attributes.bounds.match(/\d+/g).map(Number);
    assert.ok(right <= screenshot.width && bottom <= screenshot.height);
    const rgb = [5, 7, 9].map(end => parseInt(color.slice(end - 2, end), 16));
    let count = 0;
    for (let y = top; y < bottom; y++) for (let x = left; x < right; x++) {
      const pixel = (y * screenshot.width + x) * 4;
      if (rgb.every((value, i) => screenshot.data[pixel + i] === value)) count++;
    }
    assert.ok(count > 20, `${text}: expected glyph color absent (${count} pixels)`);
  }
}
console.log('PASS invocation theme, forwarded slot, explicit theme read, restoration and unknown-background fallback');
