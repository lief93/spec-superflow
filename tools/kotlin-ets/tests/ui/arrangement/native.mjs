import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const nodes = [];
function visit(node) {nodes.push(node.attributes); (node.children ?? []).forEach(visit);}
visit(JSON.parse(readFileSync(process.argv[2], 'utf8')));
function bounds(id) {
  const matches = nodes.filter(n => n.id === id && n.visible === 'true');
  assert.equal(matches.length, 1, id);
  return matches[0].bounds.match(/-?\d+/g).map(Number);
}
const row = ['r1', 'r2', 'r3'].map(bounds);
const column = ['c1', 'c2'].map(bounds);
const density = (row[0][2] - row[0][0]) / 24;
assert.ok(density > 0);
function near(actual, expected, label) {assert.ok(Math.abs(actual - expected) <= 1, `${label}: ${actual} vs ${expected}`);}
for (let i = 1; i < row.length; i++) {
  near(row[i][0] - row[i - 1][2], 8 * density, 'Row gap from 6 + 2');
  near(row[i][1], row[0][1], 'Row alignment');
}
near(column[1][1] - column[0][3], 12 * density, 'Column gap');
near(column[1][0], column[0][0], 'Column alignment');
for (const text of ['Spacing before', 'Spacing after'])
  assert.equal(nodes.filter(n => n.text === text && n.visible === 'true').length, 1, text);
console.log('PASS native Row 8vp and Column 12vp gaps, retained children and labels');
