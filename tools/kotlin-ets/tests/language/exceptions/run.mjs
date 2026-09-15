import { dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { verify } from '../main-path/verify.mjs';

verify(dirname(fileURLToPath(import.meta.url)), 'exceptioncases', ['Models.kt', 'Queries.kt', 'Failure.kt', 'Application.kt']);
