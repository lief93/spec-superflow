import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const texts = [];
function visit(node) {
  if (node.attributes?.type === 'Text' && node.attributes.visible === 'true') texts.push(node.attributes.text);
  for (const child of node.children ?? []) visit(child);
}
visit(JSON.parse(readFileSync(process.argv[2], 'utf8')));
assert.deepEqual(texts, process.argv[3] === 'formatted' ? ['Hello Ada: 3 items', 'Resource title'] : ['[Resource title]', 'Resource subtitle']);
console.log('PASS native resource strings consumed by Text, including a normal string-returning helper');
