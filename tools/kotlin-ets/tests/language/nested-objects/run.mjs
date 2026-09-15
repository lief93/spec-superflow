import assert from 'node:assert/strict';
import { dirname, join, resolve } from 'node:path';
import { existsSync, writeFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { verify } from '../main-path/verify.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const work = verify(here, 'nestedobjects', ['Models.kt', 'Application.kt']);
const output = join(work, 'Stateful.ets');
const args = [resolve(here, '../../../kotlin-ets'), '--mode', 'language', '--out', output, join(here, 'StatefulCompanion.kt')];
const result = spawnSync('bash', args, { encoding: 'utf8', timeout: 600000,
  env: { ...process.env, JAVA_TOOL_OPTIONS: '-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' } });
writeFileSync(join(work, 'stateful-negative.json'), JSON.stringify({ args, status: result.status, stdout: result.stdout, stderr: result.stderr }, null, 2));
assert.equal(result.status, 2, result.stdout + result.stderr);
assert.match(result.stdout, /Stateful companion initialization requires enclosing-class initialization support/);
assert.equal(existsSync(output), false);
