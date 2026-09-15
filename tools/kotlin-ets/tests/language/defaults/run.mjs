import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { verify } from '../main-path/verify.mjs';

const work = verify(dirname(fileURLToPath(import.meta.url)), 'defaultcases', ['Models.kt', 'Queries.kt', 'Application.kt']);
const models = readFileSync(join(work, 'modules/Models.ets'), 'utf8');
const queries = readFileSync(join(work, 'modules/Queries.ets'), 'utf8');
assert.match(models, /model\(extra: number\): Model;/);
assert.match(models, /function __etsDefault_Label_model\(__etsReceiver: Label, extra: number\): Model/);
assert.match(queries, /model\(extra: number\): Model/);
assert.match(queries, /__etsDefault_Left_rank\(this\).*__etsDefault_Right_rank\(this\)/);
const grandChild = queries.slice(queries.indexOf('export class GrandChild'), queries.indexOf('export class CounterValue'));
assert.ok(grandChild.length > 0);
assert.doesNotMatch(grandChild, /model\(|stage\(/);
console.log('PASS source method/parameter names, single default bodies and inherited bridge reuse');
