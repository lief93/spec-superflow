import assert from 'node:assert/strict';
import { mkdirSync, readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { spawnSync } from 'node:child_process';

assert.ok(process.argv[2], 'Install and launch the emitted Page.ets, then pass an evidence directory');
const work = resolve(process.argv[2]);
mkdirSync(work, { recursive: true });
const hdc = '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/toolchains/hdc';
function run(...args) {
  const result = spawnSync(hdc, ['-t', process.argv[3] ?? '127.0.0.1:5555', ...args], { encoding: 'utf8', timeout: 30000 });
  assert.equal(result.status, 0, result.stdout + result.stderr);
}
function dump(name) {
  const remote = `/data/local/tmp/scroll-${process.pid}.json`;
  run('shell', 'uitest', 'dumpLayout', '-a', '-b', 'com.joker.kit', '-p', remote);
  const path = join(work, `${name}.json`);
  run('file', 'recv', remote, path);
  const nodes = [];
  function visit(node) { nodes.push(node); (node.children ?? []).forEach(visit); }
  visit(JSON.parse(readFileSync(path, 'utf8')));
  return nodes;
}
const bounds = node => node.attributes.bounds.match(/-?\d+/g).map(Number);
const pause = () => new Promise(resolve => setTimeout(resolve, 700));
const before = dump('before');
const scrolls = before.filter(node => node.attributes.type === 'Scroll');
assert.equal(scrolls.length, 2, 'only the enabled vertical branch and horizontal container scroll');
const last = before.filter(node => node.attributes.text === 'Last');
assert.equal(last.length, 2, 'both conditional branches retain their content');
const [x, y, right, bottom] = bounds(scrolls[0]);
run('shell', 'uitest', 'uiInput', 'swipe', String(x + (right - x) / 2), String(bottom - 30),
  String(x + (right - x) / 2), String(y + 30), '600');
await pause();
const vertical = dump('vertical');
const moved = vertical.filter(node => node.attributes.text === 'Last');
assert.ok(bounds(moved[0])[1] < bounds(last[0])[1] - 30, 'vertical text moves up');
assert.deepEqual(bounds(moved[1]), bounds(last[1]), 'non-scroll branch stays put');
const [hx, hy, hr, hb] = bounds(scrolls[1]);
run('shell', 'uitest', 'uiInput', 'swipe', String(hr - 20), String(Math.round((hy + hb) / 2)),
  String(hx + 20), String(Math.round((hy + hb) / 2)), '600');
await pause();
assert.ok(dump('horizontal').some(node => node.attributes.text === 'Right'), 'horizontal end content becomes visible');
console.log('PASS native vertical/horizontal swipes and unchanged non-scroll branch');
