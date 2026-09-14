import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';

export const ts = createRequire(import.meta.url)(process.env.TYPESCRIPT_PATH ??
  '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js');

export function assertRuntimeHelpers(file, expected) {
  const text = readFileSync(file, 'utf8');
  const tree = ts.createSourceFile(file, text, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
  const names = tree.statements.filter(node => ts.isFunctionDeclaration(node) &&
    node.name?.text.startsWith('__ets')).map(node => node.name.text);
  assert.deepEqual(names, expected, `runtime declarations in ${file}`);
  return text;
}
