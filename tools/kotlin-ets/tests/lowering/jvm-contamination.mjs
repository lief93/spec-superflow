import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../..');
const bannedImport = /(?:^|\n)\s*import\s+org\.jetbrains\.kotlin\.backend\.jvm/;
const bannedType = /(?:^|\n)\s*(?:import\s+.*\b)?(?:JvmBackendContext|GenerationState|JvmIrCodegenFactory|JvmGeneratorExtensionsImpl|JvmIrDeserializerImpl)\b/;
const layers = ['src/lower', 'src/target', 'src/output'];
const hits = [];
function walk(directory, relative) {
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    const name = join(relative, entry.name);
    if (entry.isDirectory()) walk(path, name);
    else if (entry.name.endsWith('.kt')) {
      const text = readFileSync(path, 'utf8');
      if (bannedImport.test(text) || bannedType.test(text)) hits.push(name);
    }
  }
}
for (const layer of layers) walk(join(root, layer), layer);
assert.deepEqual(hits, [], `JVM backend contamination in ETS backend layers:\n${hits.join('\n')}`);
const adapter = readFileSync(join(root, 'src/core/OfficialLowerings.kt'), 'utf8');
assert.match(adapter, /import org\.jetbrains\.kotlin\.backend\.jvm\.JvmBackendContext/);
assert.match(adapter, /fun createJvmLoweringContext/);
const phases = readFileSync(join(root, 'src/lower/EtsLoweringPhases.kt'), 'utf8');
assert.match(phases, /object EtsLoweringPhases/);
assert.doesNotMatch(phases, bannedImport);
console.log('PASS JVM contamination gate: src/lower, src/target, src/output have no JVM backend imports');
