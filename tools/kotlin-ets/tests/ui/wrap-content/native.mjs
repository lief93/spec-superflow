import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { execFileSync } from 'node:child_process';
const hdc = '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/toolchains/hdc';
const work = mkdtempSync('/private/tmp/kotlin-ets-wrap-native-');
console.log('Native evidence: ' + work);
function run(name, args) { writeFileSync(join(work, name + '.txt'), execFileSync(hdc, args, { encoding: 'utf8', timeout: 30000 })); }
run('install', ['install', process.argv[2]]);
run('stop', ['shell', 'aa', 'force-stop', 'com.joker.kit']);
run('start', ['shell', 'aa', 'start', '-a', 'EntryAbility', '-b', 'com.joker.kit']);
await new Promise(resolve => setTimeout(resolve, 1500));
run('layout', ['shell', 'uitest', 'dumpLayout', '-a', '-b', 'com.joker.kit', '-p', '/data/local/tmp/wrap.json']);
run('receive', ['file', 'recv', '/data/local/tmp/wrap.json', join(work, 'layout.json')]);
const nodes = [];
function visit(n) { if (n.attributes) nodes.push(n.attributes); (n.children ?? []).forEach(visit); }
visit(JSON.parse(readFileSync(join(work, 'layout.json'))));
function bounds(id) {
  const node = nodes.find(n => n.id === id); assert.ok(node, id);
  return node.bounds.match(/\d+/g).map(Number);
}
const evidence = [];
for (const [name, wr, hr, xr, yr] of [['size', .25, .25, .375, .375],
  ['height', 1, .25, 0, .375], ['width', .25, 1, .75, 0]]) {
  const [x,y,r,b] = bounds(name + '-outer'), inner = bounds(name + '-inner');
  const actual = [(inner[2]-inner[0])/(r-x), (inner[3]-inner[1])/(b-y), (inner[0]-x)/(r-x), (inner[1]-y)/(b-y)];
  actual.forEach((v,i) => assert.ok(Math.abs(v-[wr,hr,xr,yr][i]) < .02, name + ': ' + actual));
  evidence.push({ name, outer:[x,y,r,b], inner, actual });
}
const first = bounds('wrap-first'), outer = bounds('size-outer');
assert.ok(Math.abs((first[2]-first[0])/(outer[2]-outer[0])-.5)<.02);
writeFileSync(join(work,'result.json'), JSON.stringify({ passed:true,evidence },null,2));
console.log('PASS native wrap axis sizes, alignment and modifier ordering');
