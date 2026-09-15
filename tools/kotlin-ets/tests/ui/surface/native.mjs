import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

assert.ok(process.argv[2] && process.argv[3], 'Pass dumpLayout -a JSON and device pixels per vp');
const density = Number(process.argv[3]);
assert.ok(density > 0);
const nodes = [];
function visit(node) { nodes.push(node); (node.children ?? []).forEach(visit); }
visit(JSON.parse(readFileSync(process.argv[2], 'utf8')));
const colors = { Inherited: '#FFFFFFFF', Override: '#FFFF0000', Basic: '#FF000000' };
for (const [text, color] of Object.entries(colors)) {
  const matches = nodes.filter(node => node.attributes.text === text);
  assert.equal(matches.length, 1, text);
  const node = matches[0];
  const [x, y, right, bottom] = node.attributes.bounds.match(/\d+/g).map(Number);
  assert.ok(Math.abs(right - x - 80 * density) <= 1, `${text} width`);
  assert.ok(Math.abs(bottom - y - 40 * density) <= 1, `${text} height`);
  assert.ok(node.extraAttrs?.FontColor?.startsWith(color), `${text} color: ${node.extraAttrs?.FontColor}`);
}
const surfaces = nodes.filter(node => node.attributes.type === '__Common__' && node.attributes.clip === 'true');
assert.equal(surfaces.length, 3);
assert.deepEqual(surfaces.map(node => node.attributes.backgroundColor), ['#FF000000', '#FF000000', '#FFFFFF00']);
assert.ok(surfaces.every(node => node.attributes.hitTestBehavior === 'HitTestMode.Default'));
assert.equal(nodes.filter(node => node.attributes.text === 'Outside').length, 1);
console.log('PASS native Surface dimensions, propagated text minima, content colors, clipping and hit-test mode');
