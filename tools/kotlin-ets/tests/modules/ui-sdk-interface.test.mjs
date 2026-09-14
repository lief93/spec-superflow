import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdirSync, mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { verifyModuleCoverage } from './ui-sdk-evidence.mjs';

// Synthetic checker records exercise the verifier contract, not SDK acceptance.
const work = mkdtempSync(join(tmpdir(), 'kotlin-ets-interface-classifier-'));
console.log(`Node fixture evidence: ${work}`);
let caseNumber = 0;
function inputs(text) {
  const ets = join(work, String(++caseNumber));
  const path = join(ets, 'modules/Contract.ets');
  const parent = join(ets, 'Consumer.ets');
  mkdirSync(join(ets, 'modules'), { recursive: true });
  writeFileSync(path, text);
  const sha256 = createHash('sha256').update(text).digest('hex');
  return {
    modules: [{ name: 'Contract.ets', path, sha256 }], ets, records: [], buildInfoPath: join(ets, '.tsbuildinfo'),
    buildInfo: { program: { fileNames: [path, parent], fileInfos: [sha256, 'parent-hash'],
      semanticDiagnosticsPerFile: [1, 2], referencedMap: [[2, 1]], fileIdsList: [[1]] } },
    checker: { fileList: {
      [path]: { error: false, parent: [parent], children: [] },
      [parent]: { error: false, parent: [], children: [path] },
    } },
  };
}
const positives = [
  ['plain interface', 'export interface Plain { value: string; }'],
  ['generic method bound import', 'import { Readable } from "./Readable"; export interface MethodPort<C> { read<R extends Readable<C>>(reader: R): C; }'],
  ['explicit type import', 'import type { Readable } from "./Readable"; export interface Port { value: Readable<string>; }'],
  ['named type specifier', 'import { type Readable } from "./Readable"; export interface Port { value: Readable<string>; }'],
  ['named alias identity', 'import { Readable as View } from "./Readable"; export interface Port { value: View<string>; }'],
  ['interface heritage', 'import { Readable } from "./Readable"; export interface Port extends Readable<string> {}'],
  ['shadow and actual type use', 'import { Readable } from "./Readable"; export interface Port { value: Readable<string>; echo<Readable>(value: Readable): Readable; }'],
];
for (const [label, text] of positives) {
  const value = inputs(text);
  assert.equal(verifyModuleCoverage(value)[0].kind, 'interface-only', label);
}
const negatives = [
  ['side effect import', 'import "./init"; export interface Port {}'],
  ['side effect alongside type import', 'import "./init"; import { View } from "./View"; export interface Port { value: View; }'],
  ['runtime class', 'export interface Port {} export class Runtime {}'],
  ['runtime variable', 'export interface Port {} export const value = 1;'],
  ['runtime function', 'export interface Port {} export function run(): void {}'],
  ['runtime expression', 'import { View } from "./View"; export interface Port { value: View; } View();'],
  ['value type query', 'import { View } from "./View"; export interface Port { value: typeof View; }'],
  ['computed property', 'import { key } from "./key"; export interface Port { [key]: string; }'],
  ['unused named import', 'import { View } from "./View"; export interface Port {}'],
  ['partly unused imports', 'import { View, Unused } from "./View"; export interface Port { value: View; }'],
  ['shadowed binder only', 'import { View } from "./View"; export interface Port { echo<View>(value: View): View; }'],
  ['property spelling only', 'import { View } from "./View"; export interface Port { View: string; }'],
  ['comment spelling only', 'import { View } from "./View"; export interface Port { /* View */ value: string; }'],
  ['default import', 'import View from "./View"; export interface Port { value: View; }'],
  ['namespace import', 'import * as View from "./View"; export interface Port { value: View.Item; }'],
  ['empty named import', 'import {} from "./init"; export interface Port {}'],
  ['import equals', 'import View = require("./View"); export interface Port { value: View; }'],
  ['reexport', 'export interface Port {} export { View } from "./View";'],
  ['no interface', 'import { View } from "./View";'],
  ['runtime enum', 'export interface Port {} export enum Value { First }'],
];
for (const [label, text] of negatives) {
  assert.throws(() => verifyModuleCoverage(inputs(text)), /Missing runtime SDK input for non-interface-only module/, label);
}
assert.throws(() => verifyModuleCoverage(inputs('export interface Broken {')), /Cannot classify erased module/);
console.log(`PASS interface classifier: ${positives.length} positives, ${negatives.length} non-erased/unsupported negatives and malformed syntax; no SDK build`);
