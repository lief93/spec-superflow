import { dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { verify } from '../main-path/verify.mjs';

verify(dirname(fileURLToPath(import.meta.url)), 'enums', ['Models.kt', 'Queries.kt', 'Application.kt'], api => {
  return ['unknown', 'broken', 'broken'].map(name => {
    try { api[name](); return 'unexpected'; } catch (failure) { return failure.name; }
  });
});
