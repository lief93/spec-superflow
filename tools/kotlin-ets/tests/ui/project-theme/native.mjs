import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {join} from 'node:path';

assert.ok(process.argv[2] && process.argv[3], 'Pass same-run dumpLayout JSON and native screenshot');
const modules = process.env.KOTLIN_ETS_NODE_MODULES ?? join(process.env.HOME,
  '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules');
const sharp = createRequire(import.meta.url)(join(modules, 'sharp'));
const {data, info} = await sharp(process.argv[3]).removeAlpha().raw().toBuffer({resolveWithObject: true});
const nodes = [];
function visit(node) {nodes.push(node); (node.children ?? []).forEach(visit);}
visit(JSON.parse(readFileSync(process.argv[2], 'utf8')));
for (const [text, rgb] of [['Project light', [18, 86, 171]], ['Project dark', [218, 52, 120]]]) {
  const matches = nodes.filter(n => n.attributes.text === text && n.attributes.visible === 'true');
  assert.equal(matches.length, 1, text);
  const [left, top, right, bottom] = matches[0].attributes.bounds.match(/\d+/g).map(Number);
  assert.ok(right <= info.width && bottom <= info.height);
  let count = 0;
  for (let y = top; y < bottom; y++) for (let x = left; x < right; x++) {
    const offset = (y * info.width + x) * info.channels;
    if (rgb.every((value, c) => Math.abs(data[offset + c] - value) <= 10)) count++;
  }
  assert.ok(count > 100, `${text}: expected native glyph color missing (${count} pixels)`);
  console.log(`${text}: ${count} matching glyph pixels`);
}
console.log('PASS native base/dark resource aliases selected independently in one page');
