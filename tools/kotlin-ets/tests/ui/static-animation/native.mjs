import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {join} from 'node:path';
const [layout, screenshot] = process.argv.slice(2);
assert.ok(layout && screenshot, 'Pass native layout and screenshot');
const nodes = [];
function visit(node) {nodes.push(node); (node.children ?? []).forEach(visit);}
visit(JSON.parse(readFileSync(layout, 'utf8')));
for (const text of ['Before', 'After']) assert.equal(nodes.filter(n =>
  n.attributes.text === text && n.attributes.visible === 'true').length, 1, text);
const modules = process.env.KOTLIN_ETS_NODE_MODULES ?? join(process.env.HOME,
  '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules');
const sharp = createRequire(import.meta.url)(join(modules, 'sharp'));
const {data, info} = await sharp(screenshot).removeAlpha().raw().toBuffer({resolveWithObject: true});
function red(x, y) {
  const p = (y * info.width + x) * info.channels;
  return data[p] > 220 && data[p + 1] < 35 && data[p + 2] < 35;
}
const circles = nodes.filter(n => n.attributes.type === 'Stack' && n.attributes.visible === 'true')
  .map(n => n.attributes.bounds.match(/\d+/g).map(Number))
  .filter(([l,t,r,b]) => r-l === 84 && b-t === 84 && red((l+r)/2, (t+b)/2));
assert.equal(circles.length, 3, 'Three 24vp circles at the 3.5-density native fixture');
assert.equal(new Set(circles.map(c => c[1])).size, 1, 'No animated vertical translation');
for (const [l,t] of circles) assert.equal(red(l + 1,t + 1), false, 'Circular background must leave its corner unpainted');
console.log('PASS three static circles, native dimensions/shape and retained sibling labels');
