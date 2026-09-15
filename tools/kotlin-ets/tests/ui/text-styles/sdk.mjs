import assert from 'node:assert/strict';
import { cpSync, mkdtempSync } from 'node:fs';
import { basename, join, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const page = resolve(process.argv[2]);
const seed = mkdtempSync('/private/tmp/kotlin-ets-font-sdk-seed-');
const base = process.env.KOTLIN_ETS_SDK_SEED ?? '/private/tmp/kotlin-ets-native-20260914-06/harmony';
const excluded = new Set(['build', '.hvigor', 'oh_modules', '.idea', '.migration', '.git']);
cpSync(base, seed, { recursive: true, filter: path => !excluded.has(basename(path)) });
cpSync(page + '.resources/rawfile', join(seed, 'entry/src/main/resources/rawfile'), { recursive: true });
const result = spawnSync(process.execPath, [join(dirname(fileURLToPath(import.meta.url)), '../basic-controls-sdk.mjs'), page],
  { env: { ...process.env, KOTLIN_ETS_SDK_SEED: seed }, stdio: 'inherit', timeout: 600000 });
assert.equal(result.status, 0);
console.log('PASS unchanged text-style page with referenced fonts in SDK host');
