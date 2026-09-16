import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { execFileSync } from 'node:child_process';
import { createRequire } from 'node:module';
const require = createRequire('/Users/lief123/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/package.json');
const sharp = require('sharp');
const hdc = '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/toolchains/hdc';
const work = mkdtempSync('/private/tmp/kotlin-ets-material-button-native-');
console.log('Native evidence: ' + work);
assert.ok(process.argv[2]);
function run(name, args) { writeFileSync(join(work, name + '.txt'), execFileSync(hdc, args, { encoding: 'utf8', timeout: 30000 })); }
run('install', ['install', process.argv[2]]);
run('stop', ['shell', 'aa', 'force-stop', 'com.joker.kit']);
run('start', ['shell', 'aa', 'start', '-a', 'EntryAbility', '-b', 'com.joker.kit']);
await new Promise(resolve => setTimeout(resolve, 1500));
function layout(name) {
  const path = '/data/local/tmp/' + name + '.json';
  run(name, ['shell', 'uitest', 'dumpLayout', '-a', '-b', 'com.joker.kit', '-p', path]);
  run(name + '-recv', ['file', 'recv', path, join(work, name + '.json')]);
  const nodes = [];
  function visit(node) { if (node.attributes) nodes.push(node.attributes); (node.children ?? []).forEach(visit); }
  visit(JSON.parse(readFileSync(join(work, name + '.json'))));
  return nodes;
}
const nodes = layout('initial');
function node(id, values = nodes) { const result = values.find(n => n.id === id); assert.ok(result, id); return result; }
function bounds(id) { return node(id).bounds.match(/\d+/g).map(Number); }
assert.equal(node('count').text, 'Count: 0');
run('screenshot', ['shell', 'snapshot_display', '-f', '/data/local/tmp/material-button.jpeg']);
run('receive-image', ['file', 'recv', '/data/local/tmp/material-button.jpeg', join(work, 'screen.jpeg')]);
const { data, info } = await sharp(join(work, 'screen.jpeg')).removeAlpha().raw().toBuffer({ resolveWithObject: true });
const colors = [];
for (const [id, channel] of [['active', 0], ['disabled', 2]]) {
  const [x, y, right, bottom] = bounds(id);
  assert.ok(Math.abs((bottom - y) / (right - x) - 52 / 240) < .02, `${id} content padding/minimum size`);
  const px = Math.round(x + (right - x) / 8), py = Math.round((y + bottom) / 2);
  const rgb = Array.from(data.subarray((py * info.width + px) * info.channels, (py * info.width + px) * info.channels + 3));
  assert.ok(rgb[channel] > 220 && rgb.every((v, c) => c === channel || v < 35), `${id} color ${rgb}`);
  colors.push({ id, rgb, bounds: [x, y, right, bottom] });
}
for (const [id, count] of [['disabled', 0], ['active', 1], ['text-button', 2]]) {
  const [x, y, right, bottom] = bounds(id);
  run('click-' + id, ['shell', 'uitest', 'uiInput', 'click', String(Math.round((x + right) / 2)), String(Math.round((y + bottom) / 2))]);
  await new Promise(resolve => setTimeout(resolve, 400));
  assert.equal(node('count', layout('after-' + id)).text, 'Count: ' + count);
}
writeFileSync(join(work, 'result.json'), JSON.stringify({ passed: true, colors, counts: [0, 1, 2] }, null, 2));
console.log('PASS native material button colors, padding, disabled click suppression and source callback forwarding');
