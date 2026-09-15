import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { createRequire } from 'node:module';

const require = createRequire('/Users/lief123/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/package.json');
const sharp = require('sharp');
const execute = promisify(execFile);
const hdc = '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/toolchains/hdc';
const work = mkdtempSync('/private/tmp/kotlin-ets-async-native-');
const records = [], pending = new Map();
console.log('Native evidence: ' + work);
assert.ok(process.argv[2], 'Pass unchanged fixture HAP with INTERNET permission');
async function command(label, args) {
  const result = await execute(hdc, args, { timeout: 30000 });
  writeFileSync(join(work, label + '.txt'), result.stdout + result.stderr);
  return result.stdout;
}
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const server = createServer((req, res) => {
  records.push({ path: req.url, time: Date.now() });
  pending.set(req.url, res);
});
await new Promise(resolve => server.listen(18987, '127.0.0.1', resolve));
async function requested(path) {
  for (let i = 0; i < 200 && !pending.has(path); i++) await delay(100);
  assert.ok(pending.has(path), 'Native Image must request ' + path);
}
function release(path, color) {
  const res = pending.get(path);
  res.writeHead(200, { 'Content-Type': 'image/svg+xml', 'Cache-Control': 'no-store' });
  res.end(`<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96"><path fill="${color}" d="M0 0H96V96H0Z"/></svg>`);
}
async function screenshot(label) {
  const remote = '/data/local/tmp/' + label + '.jpeg';
  await command(label + '-capture', ['shell', 'snapshot_display', '-f', remote]);
  const path = join(work, label + '.jpeg');
  await command(label + '-recv', ['file', 'recv', remote, path]);
  const pixels = await sharp(path).ensureAlpha().raw().toBuffer();
  const counts = { green: 0, red: 0, blue: 0, blend: 0 };
  for (let i = 0; i < pixels.length; i += 4) {
    const [r, g, b] = pixels.subarray(i, i + 3);
    if (g > 240 && r < 10 && b < 10) counts.green++;
    if (r > 240 && g < 10 && b < 10) counts.red++;
    if (b > 240 && r < 10 && g < 10) counts.blue++;
    if (r > 15 && g > 15 && r < 240 && g < 240 && b < 10) counts.blend++;
  }
  writeFileSync(join(work, label + '-pixels.json'), JSON.stringify(counts));
  return counts;
}
try {
  await command('reverse', ['rport', 'tcp:18987', 'tcp:18987']);
  // Reinstall without app data: native Image may retain decoded URLs across runs.
  await command('uninstall', ['uninstall', 'com.joker.kit']);
  await command('install', ['install', process.argv[2]]);
  await command('stop', ['shell', 'aa', 'force-stop', 'com.joker.kit']);
  await command('start', ['shell', 'aa', 'start', '-a', 'EntryAbility', '-b', 'com.joker.kit']);
  await requested('/a.svg');
  await delay(500);
  const before = await screenshot('placeholder');
  assert.ok(before.green > 50000, JSON.stringify(before));
  release('/a.svg', '#ff0000');
  await delay(180);
  const during = await screenshot('crossfade');
  await delay(900);
  const after = await screenshot('loaded');
  assert.ok(after.red > 50000 && after.green < 100, JSON.stringify(after));
  await command('layout', ['shell', 'uitest', 'dumpLayout', '-a', '-b', 'com.joker.kit', '-p', '/data/local/tmp/async-layout.json']);
  const layout = join(work, 'layout.json');
  await command('layout-recv', ['file', 'recv', '/data/local/tmp/async-layout.json', layout]);
  let button;
  function walk(node) {
    if (!node || typeof node !== 'object') return;
    if (node.attributes?.text === 'Change') button = node.attributes;
    Object.values(node).forEach(walk);
  }
  walk(JSON.parse(readFileSync(layout)));
  assert.ok(button);
  const [x1, y1, x2, y2] = button.bounds.match(/\d+/g).map(Number);
  await command('change', ['shell', 'uitest', 'uiInput', 'click', String(Math.round((x1 + x2) / 2)), String(Math.round((y1 + y2) / 2))]);
  await requested('/b.svg');
  const changing = await screenshot('new-placeholder');
  assert.ok(changing.green > 50000, JSON.stringify(changing));
  release('/b.svg', '#0000ff');
  await delay(1000);
  const second = await screenshot('second-loaded');
  assert.ok(second.blue > 50000 && second.green < 100, JSON.stringify(second));
  const result = { passed: true, before, during, after, changing, second, requests: records };
  writeFileSync(join(work, 'result.json'), JSON.stringify(result, null, 2));
  console.log('PASS native SVG loading, placeholder removal, request replacement and pixel checks; mid-fade pixels recorded');
} finally {
  writeFileSync(join(work, 'requests.json'), JSON.stringify(records, null, 2));
  server.closeAllConnections();
  await new Promise(resolve => server.close(resolve));
  await command('reverse-remove', ['fport', 'rm', 'tcp:18987', 'tcp:18987']).catch(() => {});
}
