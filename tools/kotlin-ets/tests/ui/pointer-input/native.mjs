import assert from 'node:assert/strict';
import { mkdirSync, readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { spawnSync } from 'node:child_process';

assert.ok(process.argv[2], 'Install and launch pointerinput.Page, then pass evidence directory');
const work = resolve(process.argv[2]);
mkdirSync(work, { recursive: true });
const hdc = '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/toolchains/hdc';
function run(...args) {
  const result = spawnSync(hdc, ['-t', process.argv[3] ?? '127.0.0.1:5555', ...args], { encoding: 'utf8', timeout: 30000 });
  assert.equal(result.status, 0, result.stdout + result.stderr);
}
function dump(name) {
  const remote = `/data/local/tmp/pointer-input-${process.pid}.json`;
  run('shell', 'uitest', 'dumpLayout', '-a', '-b', 'com.joker.kit', '-p', remote);
  const path = join(work, `${name}.json`);
  run('file', 'recv', remote, path);
  const nodes = [];
  function visit(node) { nodes.push(node); (node.children ?? []).forEach(visit); }
  visit(JSON.parse(readFileSync(path, 'utf8')));
  return nodes;
}
const text = (nodes, label) => nodes.find(node => node.attributes.text === label);
const bounds = node => node.attributes.bounds.match(/-?\d+/g).map(Number);
async function click(x, y) {
  run('shell', 'uitest', 'uiInput', 'click', String(Math.round(x)), String(Math.round(y)));
  await new Promise(resolve => setTimeout(resolve, 500));
}
const before = dump('before');
assert.ok(text(before, 'Behind 0'));
assert.ok(text(before, 'Inside 0'));
const behindLabel = text(before, 'Behind button');
const contains = (node, child) => node === child || (node.children ?? []).some(item => contains(item, child));
const behind = before.find(node => node.attributes.type === 'Button' &&
  contains(node, behindLabel));
assert.ok(behind, 'underlying button is still generated');
const [left, top, right, bottom] = bounds(behind);
await click((left + right) / 2, bottom - (bottom - top) / 5);
const blocked = dump('blocked');
assert.ok(text(blocked, 'Behind 0'), 'overlay must block the underlying button');
const [il, it, ir, ib] = bounds(text(blocked, 'Inside button'));
await click((il + ir) / 2, (it + ib) / 2);
const child = dump('child');
assert.ok(text(child, 'Inside 1'), 'overlay child must remain interactive');
assert.ok(text(child, 'Behind 0'));
console.log('PASS native overlay blocks lower sibling and preserves child interaction');
