import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

assert.ok(process.argv[2] && process.argv[3], 'Pass native dumpLayout JSON and px per vp');
const density = Number(process.argv[3]);
assert.ok(density > 0);
const nodes = [];
function visit(node) { nodes.push(node); (node.children ?? []).forEach(visit); }
visit(JSON.parse(readFileSync(process.argv[2], 'utf8')));
function bounds(id) {
  const matches = nodes.filter(node => node.attributes.id === id);
  assert.equal(matches.length, 1, id);
  return matches[0].attributes.bounds.match(/\d+/g).map(Number);
}
const cases = { column: [40,0], row: [0,25], 'top-start': [0,0], 'top-center': [40,0],
  'top-end': [80,0], 'center-start': [0,25], center: [40,25], 'center-end': [80,25],
  'bottom-start': [0,50], 'bottom-center': [40,50], 'bottom-end': [80,50] };
for (const [id, [dx,dy]] of Object.entries(cases)) {
  const [x,y,right,bottom] = bounds(id);
  const [cx,cy,cr,cb] = bounds(id + '-child');
  for (const [actual, expected] of [[right-x,100], [bottom-y,60], [cx-x,dx], [cy-y,dy], [cr-cx,20], [cb-cy,10]])
    assert.ok(Math.abs(actual - expected * density) <= 1, `${id}: ${actual}px, expected ${expected}vp`);
}
console.log('PASS native LTR Column/Row cross-axis and all nine Box child positions');
