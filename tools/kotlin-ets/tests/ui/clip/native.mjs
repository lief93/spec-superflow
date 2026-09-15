import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { execFileSync } from 'node:child_process';
import { createRequire } from 'node:module';
const require = createRequire('/Users/lief123/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/package.json');
const sharp = require('sharp');
const hdc = '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/toolchains/hdc';
const work = mkdtempSync('/private/tmp/kotlin-ets-clip-native-');
console.log('Native evidence: ' + work);
assert.ok(process.argv[2]);
function run(name, args) { writeFileSync(join(work, name + '.txt'), execFileSync(hdc, args, { encoding: 'utf8', timeout: 30000 })); }
run('install', ['install', process.argv[2]]);
run('stop', ['shell', 'aa', 'force-stop', 'com.joker.kit']);
run('start', ['shell', 'aa', 'start', '-a', 'EntryAbility', '-b', 'com.joker.kit']);
await new Promise(resolve => setTimeout(resolve, 1500));
run('layout', ['shell', 'uitest', 'dumpLayout', '-a', '-b', 'com.joker.kit', '-p', '/data/local/tmp/clip.json']);
run('receive-layout', ['file', 'recv', '/data/local/tmp/clip.json', join(work, 'layout.json')]);
run('screenshot', ['shell', 'snapshot_display', '-f', '/data/local/tmp/clip.jpeg']);
run('receive-image', ['file', 'recv', '/data/local/tmp/clip.jpeg', join(work, 'screen.jpeg')]);
const nodes = [];
function visit(node) { if (node.attributes?.id) nodes.push(node.attributes); (node.children ?? []).forEach(visit); }
visit(JSON.parse(readFileSync(join(work, 'layout.json'))));
const { data, info } = await sharp(join(work, 'screen.jpeg')).removeAlpha().raw().toBuffer({ resolveWithObject: true });
const results = [];
for (const [id, index, channel, expected] of [['circle', 0, 0, Math.PI / 4], ['capsule', 0, 2, .5 + Math.PI / 8],
  ['outside', 0, 1, 1], ['padded', 0, 0, Math.PI / 4], ['circle', 1, 0, 1]]) {
  const node = nodes.filter(n => n.id === id)[index];
  assert.ok(node, id);
  const [x, y, right, bottom] = node.bounds.match(/\d+/g).map(Number);
  let colored = 0;
  for (let py = y; py < bottom; py++) for (let px = x; px < right; px++) {
    const pixel = Array.from(data.subarray((py * info.width + px) * info.channels, (py * info.width + px) * info.channels + 3));
    if (pixel[channel] > 220 && pixel.every((v, c) => c === channel || v < 35)) colored++;
  }
  const ratio = colored / ((right - x) * (bottom - y));
  assert.ok(Math.abs(ratio - expected) < .045, `${id}[${index}] ratio ${ratio}, expected ${expected}`);
  results.push({ id, index, ratio, expected, bounds: [x, y, right, bottom] });
}
writeFileSync(join(work, 'result.json'), JSON.stringify({ passed: true, results }, null, 2));
console.log('PASS native circle/capsule/rectangle pixels, outer background and padding boundaries');
