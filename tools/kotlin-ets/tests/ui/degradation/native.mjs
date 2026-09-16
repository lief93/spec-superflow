import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const layout = JSON.parse(readFileSync(process.argv[2], 'utf8'));
const labels = [];
function visit(node) {
  if (node.attributes?.text) labels.push(node.attributes);
  for (const child of node.children ?? []) visit(child);
}
visit(layout);
assert.deepEqual(labels.map(node => node.text), ['Before', 'After']);
const boxes = labels.map(node => node.bounds.match(/\d+/g).map(Number));
for (const [left, top, right, bottom] of boxes) assert.ok(right > left && bottom > top);
assert.ok(boxes[0][3] <= boxes[1][1], 'preserved siblings must not overlap');
assert.ok(boxes[0][0] > boxes[1][0], 'first label retains padding');
console.log('PASS native labels, nonempty bounds, padding and sibling order');
