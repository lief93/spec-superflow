import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

const SHA256_PATTERN = /^[a-f0-9]{64}$/;
const FORBIDDEN_ENTRY = /(^|\/)(?:\.DS_Store|\._[^/]+|\.![^/]*!\.DS_Store)$/;

function readJson(filePath, label) {
  if (!existsSync(filePath)) {
    throw new Error(`Missing ${label}: ${filePath}`);
  }
  try {
    return JSON.parse(readFileSync(filePath, 'utf8'));
  } catch (error) {
    throw new Error(`Invalid ${label}: ${error.message}`);
  }
}

function sha256(filePath) {
  return createHash('sha256').update(readFileSync(filePath)).digest('hex');
}

function parseChecksum(filePath) {
  if (!existsSync(filePath)) {
    throw new Error(`Missing SHA256SUMS: ${filePath}`);
  }
  const lines = readFileSync(filePath, 'utf8')
    .split(/\r?\n/)
    .map((line) => line.trimEnd())
    .filter(Boolean);
  if (lines.length !== 1) {
    throw new Error('SHA256SUMS must contain exactly one package record');
  }
  const match = /^([a-f0-9]{64}) {2}(.+)$/.exec(lines[0]);
  if (!match) {
    throw new Error('SHA256SUMS record must be "<sha256>  <filename>"');
  }
  return { digest: match[1], filename: match[2] };
}

function listArchive(packagePath) {
  try {
    return execFileSync('tar', ['-tzf', packagePath], {
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'pipe'],
    }).split(/\r?\n/).filter(Boolean);
  } catch (error) {
    const detail = error.stderr?.toString().trim() || error.message;
    throw new Error(`Package archive is unreadable: ${detail}`);
  }
}

function readPackageManifest(packagePath) {
  try {
    const content = execFileSync(
      'tar',
      ['-xOzf', packagePath, 'package/package.json'],
      { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] },
    );
    return JSON.parse(content);
  } catch (error) {
    const detail = error.stderr?.toString().trim() || error.message;
    throw new Error(`Package archive has no valid package/package.json: ${detail}`);
  }
}

export function verifyOfflineBundleIntegrity(bundleDir, expected) {
  const manifest = readJson(join(bundleDir, 'manifest.json'), 'manifest.json');
  const expectedFilename = `${expected.name}-${expected.version}.tgz`;
  const expectedFields = [
    ['name', expected.name],
    ['version', expected.version],
    ['node', expected.node],
    ['package', expectedFilename],
    ['pluginPathAfterExtraction', 'package/'],
  ];

  for (const [field, value] of expectedFields) {
    if (manifest[field] !== value) {
      throw new Error(
        `manifest.json ${field} mismatch: expected ${value}, found ${manifest[field]}`,
      );
    }
  }
  if (!SHA256_PATTERN.test(manifest.sha256 || '')) {
    throw new Error('manifest.json sha256 must be a lowercase SHA-256 digest');
  }

  const checksum = parseChecksum(join(bundleDir, 'SHA256SUMS'));
  if (checksum.filename !== expectedFilename) {
    throw new Error(
      `SHA256SUMS filename mismatch: expected ${expectedFilename}, found ${checksum.filename}`,
    );
  }
  if (checksum.digest !== manifest.sha256) {
    throw new Error('SHA256SUMS digest does not match manifest.json sha256');
  }

  const packagePath = join(bundleDir, expectedFilename);
  if (!existsSync(packagePath)) {
    throw new Error(`Missing package archive: ${packagePath}`);
  }
  const actualDigest = sha256(packagePath);
  if (actualDigest !== manifest.sha256) {
    throw new Error(
      `Package SHA-256 mismatch: expected ${manifest.sha256}, found ${actualDigest}`,
    );
  }

  const entries = listArchive(packagePath);
  if (!entries.includes('package/package.json')) {
    throw new Error('Package archive is missing package/package.json');
  }
  for (const entry of entries) {
    if (entry.startsWith('/') || entry.split('/').includes('..')) {
      throw new Error(`Unsafe package entry: ${entry}`);
    }
    if (FORBIDDEN_ENTRY.test(entry)) {
      throw new Error(`Forbidden package entry: ${entry}`);
    }
  }

  const packaged = readPackageManifest(packagePath);
  const packagedFields = [
    ['name', expected.name, packaged.name],
    ['version', expected.version, packaged.version],
    ['engines.node', expected.node, packaged.engines?.node],
  ];
  for (const [field, value, actual] of packagedFields) {
    if (actual !== value) {
      throw new Error(
        `package/package.json ${field} mismatch: expected ${value}, found ${actual}`,
      );
    }
  }

  return { manifest, checksum, packagePath, entries };
}
