import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
const nodes = new Map();
function visit(node) {
  if (node.attributes?.id) nodes.set(node.attributes.id, node.attributes);
  (node.children ?? []).forEach(visit);
}
visit(JSON.parse(readFileSync(process.argv[2])));
const density = Number(process.argv[3]);
assert.ok(density > 0);
function bounds(id) {
  assert.ok(nodes.has(id), 'missing native node ' + id);
  const [x, y, right, bottom] = nodes.get(id).bounds.match(/-?\d+/g).map(Number).map(n => n / density);
  return { x, y, w: right - x, h: bottom - y };
}
function near(actual, expected) { assert.ok(Math.abs(actual - expected) < 1, `${actual} != ${expected}`); }
near(bounds('column').h, 300);
near(bounds('fixed').h, 30);
near(bounds('weightedOuter').h, 90);
near(bounds('weightedInner').h, 74);
near(bounds('weightedInner').w, 64);
near(bounds('weightedTwo').h, 180);
near(bounds('rowFixed').w, 30);
near(bounds('rowOne').w, 90);
near(bounds('rowTwo').w, 180);
near(bounds('weightedInner').y - bounds('weightedOuter').y, 8);
console.log('PASS native remaining-space 1:2 allocation on both axes, fixed sibling and inner padding constraints');
