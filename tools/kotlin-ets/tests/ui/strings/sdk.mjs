import assert from 'node:assert/strict';
import { cpSync, mkdtempSync, readFileSync, writeFileSync, mkdirSync, readdirSync, existsSync } from 'node:fs';
import { basename, join, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const page = resolve(process.argv[2]);
const resources = page + '.resources';
const seed = mkdtempSync('/private/tmp/kotlin-ets-string-sdk-seed-');
const base = process.env.KOTLIN_ETS_SDK_SEED ?? '/private/tmp/kotlin-ets-native-20260914-06/harmony';
const excluded = new Set(['build', '.hvigor', 'oh_modules', '.idea', '.migration', '.git']);
cpSync(base, seed, { recursive: true, filter: path => !excluded.has(basename(path)) });
for (const qualifier of readdirSync(resources)) {
  const source = join(resources, qualifier, 'element/string.json');
  const destination = join(seed, 'entry/src/main/resources', qualifier, 'element/string.json');
  const existing = existsSync(destination) ? JSON.parse(readFileSync(destination)).string : [];
  const generated = JSON.parse(readFileSync(source)).string;
  assert.ok(generated.every(item => !existing.some(old => old.name === item.name)), 'Resource collision');
  mkdirSync(dirname(destination), { recursive: true });
  writeFileSync(destination, JSON.stringify({ string: [...existing, ...generated] }));
}
const result = spawnSync(process.execPath, [join(dirname(fileURLToPath(import.meta.url)), '../basic-controls-sdk.mjs'), page],
  { env: { ...process.env, KOTLIN_ETS_SDK_SEED: seed }, stdio: 'inherit', timeout: 600000 });
assert.equal(result.status, 0);
console.log('PASS unchanged string-resource page with generated resource entries merged into SDK host');
