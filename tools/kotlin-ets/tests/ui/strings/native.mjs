import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const texts = [];
function visit(node) {
  if (node.attributes?.type === 'Text' && node.attributes.visible === 'true') texts.push(node.attributes.text);
  for (const child of node.children ?? []) visit(child);
}
visit(JSON.parse(readFileSync(process.argv[2], 'utf8')));
assert.deepEqual(texts, ['[Resource title]', 'Resource subtitle']);
console.log('PASS native resource strings consumed by Text, including a normal string-returning helper');
