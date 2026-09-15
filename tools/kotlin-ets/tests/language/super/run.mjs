import { dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { verify } from '../main-path/verify.mjs';

verify(dirname(fileURLToPath(import.meta.url)), 'supercases', ['Models.kt', 'Trace.kt', 'Queries.kt', 'Application.kt']);
