import assert from 'node:assert/strict';
import { mkdirSync, readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { spawnSync } from 'node:child_process';

assert.ok(process.argv[2], 'Install and launch generated constraints.Page, then pass evidence directory');
const work = resolve(process.argv[2]);
mkdirSync(work, { recursive: true });
const hdc = '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/toolchains/hdc';
function run(...args) {
  const result = spawnSync(hdc, ['-t', process.argv[3] ?? '127.0.0.1:5555', ...args], { encoding: 'utf8', timeout: 30000 });
  assert.equal(result.status, 0, result.stdout + result.stderr);
}
function dump(name) {
  const remote = `/data/local/tmp/constraints-${process.pid}.json`;
  run('shell', 'uitest', 'dumpLayout', '-a', '-b', 'com.joker.kit', '-p', remote);
  const path = join(work, `${name}.json`);
  run('file', 'recv', remote, path);
  const nodes = [];
  function visit(node) { nodes.push(node); (node.children ?? []).forEach(visit); }
  visit(JSON.parse(readFileSync(path, 'utf8')));
  return nodes;
}
const bounds = node => node.attributes.bounds.match(/-?\d+/g).map(Number);
const text = (nodes, label) => nodes.find(node => node.attributes.text === label);
const halfWidth = nodes => {
  const found = nodes.find(node => node.attributes.id === 'halfWidth');
  assert.ok(found, 'measured child exists');
  const [left, , right] = bounds(found);
  return right - left;
};
async function click(nodes, label) {
  const [left, top, right, bottom] = bounds(text(nodes, label));
  run('shell', 'uitest', 'uiInput', 'click', String(Math.round((left + right) / 2)), String(Math.round((top + bottom) / 2)));
  await new Promise(resolve => setTimeout(resolve, 700));
}
const before = dump('before');
assert.ok(text(before, 'Before'));
assert.ok(text(before, 'Width 120'));
assert.ok(text(before, 'Narrow'));
assert.equal(text(before, 'Wide'), undefined);
await click(before, 'Resize');
const resized = dump('resized');
assert.ok(text(resized, 'Width 240'));
assert.ok(text(resized, 'Wide'));
assert.equal(text(resized, 'Narrow'), undefined);
assert.ok(Math.abs(halfWidth(resized) - 2 * halfWidth(before)) <= 2);
await click(resized, 'Relabel');
const relabeled = dump('relabeled');
assert.ok(text(relabeled, 'After'), 'captured argument updates even when constraints stay constant');
assert.equal(text(relabeled, 'Before'), undefined);
assert.equal(halfWidth(relabeled), halfWidth(resized));
console.log('PASS native parent resize, constraint-driven branch and width, captured parameter update');
