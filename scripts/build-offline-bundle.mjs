#!/usr/bin/env node

import { execFileSync } from 'node:child_process';
import {
  copyFileSync,
  mkdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from 'node:fs';
import { createHash } from 'node:crypto';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const pkg = JSON.parse(readFileSync(join(ROOT, 'package.json'), 'utf8'));
const outputArg = process.argv.indexOf('--output');
const outputDir = resolve(
  outputArg >= 0 && process.argv[outputArg + 1]
    ? process.argv[outputArg + 1]
    : join(ROOT, 'release-assets', `v${pkg.version}`),
);

rmSync(outputDir, { recursive: true, force: true });
mkdirSync(outputDir, { recursive: true });

const packOutput = execFileSync(
  'npm',
  ['pack', '--pack-destination', outputDir, '--json'],
  { cwd: ROOT, encoding: 'utf8' },
);
const [{ filename }] = JSON.parse(packOutput);
const packagePath = join(outputDir, filename);
const checksum = createHash('sha256')
  .update(readFileSync(packagePath))
  .digest('hex');

copyFileSync(
  join(ROOT, 'docs', 'offline-install-zh.md'),
  join(outputDir, 'README-zh.md'),
);
writeFileSync(
  join(outputDir, 'SHA256SUMS'),
  `${checksum}  ${filename}\n`,
);
writeFileSync(
  join(outputDir, 'manifest.json'),
  `${JSON.stringify({
    name: pkg.name,
    version: pkg.version,
    node: pkg.engines.node,
    package: filename,
    sha256: checksum,
    pluginPathAfterExtraction: 'package/',
  }, null, 2)}\n`,
);

console.log(`Offline bundle created: ${outputDir}`);
console.log(`Package: ${filename}`);
console.log(`SHA-256: ${checksum}`);
