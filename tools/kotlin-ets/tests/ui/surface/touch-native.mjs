import assert from 'node:assert/strict';
import { mkdirSync, readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { spawnSync } from 'node:child_process';

assert.ok(process.argv[2], 'Pass evidence directory; install and launch generated TouchPage first');
const work = resolve(process.argv[2]);
mkdirSync(work, { recursive: true });
const hdc = '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/toolchains/hdc';
const target = process.argv[3] ?? '127.0.0.1:5555';
function run(...args) {
  const result = spawnSync(hdc, ['-t', target, ...args], { encoding: 'utf8', timeout: 30000 });
  assert.equal(result.status, 0, result.stdout + result.stderr);
}
const pause = () => new Promise(resolve => setTimeout(resolve, 500));
function dump(name) {
  const remote = `/data/local/tmp/surface-touch-${process.pid}.json`;
  run('shell', 'uitest', 'dumpLayout', '-a', '-b', 'com.joker.kit', '-p', remote);
  const path = join(work, name + '.json');
  run('file', 'recv', remote, path);
  const nodes = [];
  function visit(node) { nodes.push(node); (node.children ?? []).forEach(visit); }
  visit(JSON.parse(readFileSync(path, 'utf8')));
  return nodes;
}
function text(nodes, label) {
  const matches = nodes.filter(node => node.attributes.text === label);
  assert.equal(matches.length, 1, `Expected ${label}`);
  return matches[0];
}
function bounds(node) { return node.attributes.bounds.match(/-?\d+/g).map(Number); }
const before = dump('before');
text(before, 'Inside 0');
text(before, 'Behind 0');
const [x, y, right, bottom] = bounds(text(before, 'Inside'));
run('shell', 'uitest', 'uiInput', 'click', String(Math.round((x + right) / 2)), String(Math.round((y + bottom) / 2)));
await pause();
const clicked = dump('child-click');
text(clicked, 'Inside 1');
text(clicked, 'Behind 0');
const surface = clicked.filter(node => node.attributes.type === '__Common__' && node.attributes.clip === 'true');
assert.equal(surface.length, 1);
const [sx, sy, sr, sb] = bounds(surface[0]);
// The lower button covers the whole Surface; this point is below the child button.
run('shell', 'uitest', 'uiInput', 'click', String(Math.round((sx + sr) / 2)), String(sb - 10));
await pause();
const blank = dump('blank-click');
text(blank, 'Inside 1');
text(blank, 'Behind 0');
assert.ok(sb - 10 > sy);
console.log('PASS Surface child button responds; lower button stays untouched on child and blank-area taps');
