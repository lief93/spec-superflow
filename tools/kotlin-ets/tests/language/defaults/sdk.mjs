import { dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { verifySdk } from '../main-path/sdk.mjs';

verifySdk(dirname(fileURLToPath(import.meta.url)), process.argv[2], 'defaults');
