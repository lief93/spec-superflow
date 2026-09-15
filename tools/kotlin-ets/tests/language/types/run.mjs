import { dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { verify } from '../main-path/verify.mjs';

verify(dirname(fileURLToPath(import.meta.url)), 'typecases', ['Models.kt', 'Queries.kt', 'Application.kt'], api => {
  return ['nullFailure', 'castFailure', 'nullCastFailure'].map(name => {
    try { api[name](); return 'unexpected'; } catch (failure) { return failure.name; }
  });
});
