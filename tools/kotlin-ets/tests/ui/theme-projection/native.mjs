import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {join} from 'node:path';
const [before, after, screenshot] = process.argv.slice(2);
assert.ok(before && after && screenshot, 'Pass native layouts before/after tapping Advance and the after screenshot');
function texts(path) {
  const result = [];
  function visit(node) {
    if (node.attributes.visible === 'true' && node.attributes.text) result.push(node.attributes.text);
    (node.children ?? []).forEach(visit);
  }
  visit(JSON.parse(readFileSync(path, 'utf8')));
  return result;
}
const initial = texts(before);
const changed = texts(after);
for (const list of [initial, changed]) {
  assert.ok(list.includes('Preserved content'));
  assert.ok(list.includes('Advance'));
}
assert.ok(initial.includes('First') && !initial.includes('Next'));
assert.ok(changed.includes('Next') && !changed.includes('First'));
const nodes = [];
function visit(node) {nodes.push(node); (node.children ?? []).forEach(visit);}
visit(JSON.parse(readFileSync(after, 'utf8')));
const title = nodes.find(n => n.attributes.text === 'Preserved content');
const modules = process.env.KOTLIN_ETS_NODE_MODULES ?? join(process.env.HOME,
  '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules');
const sharp = createRequire(import.meta.url)(join(modules, 'sharp'));
const {data, info} = await sharp(screenshot).removeAlpha().raw().toBuffer({resolveWithObject: true});
const [left, top, right, bottom] = title.attributes.bounds.match(/\d+/g).map(Number);
assert.ok(right <= info.width && bottom <= info.height);
let matchingPixels = 0;
for (let y = top; y < bottom; y++) for (let x = left; x < right; x++) {
  const offset = (y * info.width + x) * info.channels;
  if ([18, 86, 171].every((value, channel) => Math.abs(data[offset + channel] - value) <= 10)) matchingPixels++;
}
assert.ok(matchingPixels > 100, 'Configured project primary must color actual native glyphs');
console.log('PASS content, native click/state/condition and project primary pixels: ' + matchingPixels);
