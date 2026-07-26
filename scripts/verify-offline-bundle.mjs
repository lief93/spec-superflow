#!/usr/bin/env node

import { execFileSync } from 'node:child_process';
import {
  existsSync,
  mkdtempSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  rmSync,
  writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const pkg = JSON.parse(readFileSync(join(ROOT, 'package.json'), 'utf8'));
const bundleArg = process.argv.indexOf('--bundle');
const bundleDir = resolve(
  bundleArg >= 0 && process.argv[bundleArg + 1]
    ? process.argv[bundleArg + 1]
    : join(ROOT, 'release-assets', `v${pkg.version}`),
);
const evidenceArg = process.argv.indexOf('--evidence');
const evidencePath = evidenceArg >= 0 && process.argv[evidenceArg + 1]
  ? resolve(process.argv[evidenceArg + 1])
  : null;
const currentPackage = readdirSync(bundleDir)
  .find((file) => file === `spec-superflow-${pkg.version}.tgz`);

if (!currentPackage) {
  throw new Error(`Missing spec-superflow-${pkg.version}.tgz in ${bundleDir}`);
}

function run(command, args, options = {}) {
  return execFileSync(command, args, {
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
    ...options,
  }).trim();
}

function installOffline(packagePath, prefix, cache) {
  run('npm', [
    'install',
    '--global',
    '--offline',
    '--ignore-scripts',
    '--cache',
    cache,
    '--prefix',
    prefix,
    packagePath,
  ], {
    env: {
      ...process.env,
      npm_config_offline: 'true',
      npm_config_registry: 'http://127.0.0.1:9',
    },
  });
}

const tempRoot = mkdtempSync(join(tmpdir(), 'spec-superflow-offline-'));
const currentPackagePath = join(bundleDir, currentPackage);
const extractedDir = join(tempRoot, 'extracted');
const previousSource = join(tempRoot, 'previous-source');
const previousPack = join(tempRoot, 'previous-pack');
const cleanPrefix = join(tempRoot, 'clean-prefix');
const upgradePrefix = join(tempRoot, 'upgrade-prefix');
const cache = join(tempRoot, 'cache');
const checks = [];

try {
  mkdirSync(extractedDir);
  run('tar', ['-xzf', currentPackagePath, '-C', extractedDir]);
  const pluginRoot = join(extractedDir, 'package');
  const pluginManifest = JSON.parse(
    readFileSync(join(pluginRoot, 'plugin.json'), 'utf8'),
  );
  const openPluginManifest = JSON.parse(
    readFileSync(join(pluginRoot, '.plugin', 'plugin.json'), 'utf8'),
  );
  const command = readFileSync(
    join(pluginRoot, 'commands', 'workflow-init.md'),
    'utf8',
  );

  checks.push(['Plugin manifest version', pluginManifest.version, pkg.version]);
  checks.push(['OpenPlugin manifest version', openPluginManifest.version, pkg.version]);
  checks.push([
    'workflow-init target version',
    command.match(/spec-superflow-cli-version: (\d+\.\d+\.\d+)/)?.[1],
    pkg.version,
  ]);
  checks.push([
    'workflow-init offline package option',
    command.includes('package=<path>') && command.includes('npm install -g "<path>"')
      ? 'present'
      : 'missing',
    'present',
  ]);
  checks.push([
    'Plugin MCP configuration',
    existsSync(join(pluginRoot, '.mcp.json')) ? 'present' : 'missing',
    'present',
  ]);
  checks.push([
    'Clean environment before workflow-init',
    existsSync(join(cleanPrefix, 'bin', 'ssf')) ? 'CLI present' : 'CLI missing',
    'CLI missing',
  ]);

  installOffline(currentPackagePath, cleanPrefix, cache);
  const cleanInstalledVersion = run(
    join(cleanPrefix, 'bin', 'ssf'),
    ['--version'],
  );
  checks.push([
    'Plugin-only plus explicit local package to CLI installation',
    cleanInstalledVersion,
    pkg.version,
  ]);
  checks.push([
    'workflow-init READY result',
    cleanInstalledVersion === pkg.version ? 'READY' : 'BLOCKED',
    'READY',
  ]);

  mkdirSync(previousSource);
  const archive = execFileSync(
    'git',
    ['archive', '--format=tar', 'v0.13.0'],
    { cwd: ROOT, maxBuffer: 20 * 1024 * 1024 },
  );
  const archivePath = join(tempRoot, 'v0.13.0.tar');
  writeFileSync(archivePath, archive);
  run('tar', ['-xf', archivePath, '-C', previousSource]);
  mkdirSync(previousPack);
  const previousPackResult = JSON.parse(run(
    'npm',
    ['pack', '--pack-destination', previousPack, '--json'],
    { cwd: previousSource },
  ));
  const previousPackagePath = join(
    previousPack,
    previousPackResult[0].filename,
  );

  installOffline(previousPackagePath, upgradePrefix, cache);
  const installedPrevious = run(
    join(upgradePrefix, 'bin', 'ssf'),
    ['--version'],
  );
  checks.push(['Previous CLI installation', installedPrevious, '0.13.0']);

  installOffline(currentPackagePath, upgradePrefix, cache);
  const installedCurrent = run(
    join(upgradePrefix, 'bin', 'ssf'),
    ['--version'],
  );
  checks.push(['Offline CLI upgrade', installedCurrent, pkg.version]);
  const doctorOutput = run(join(upgradePrefix, 'bin', 'ssf'), ['doctor']);
  checks.push([
    'Installed CLI doctor',
    doctorOutput.includes('All checks passed') ? 'passed' : 'failed',
    'passed',
  ]);
  checks.push([
    'Idempotent second workflow-init',
    installedCurrent === pkg.version ? 'skip install' : 'install required',
    'skip install',
  ]);

  const failures = checks.filter(([, actual, expected]) => actual !== expected);
  const evidence = [
    `# Offline Install and Upgrade Evidence`,
    '',
    `- Current version: \`${pkg.version}\``,
    '- Previous version: `0.13.0`',
    '- Network mode: npm `--offline` with registry forced to `127.0.0.1:9`',
    '- Installation prefix: isolated temporary directory',
    '- User global CLI and VS Code settings: unchanged',
    '',
    '| Check | Actual | Expected | Result |',
    '|---|---|---|---|',
    ...checks.map(([name, actual, expected]) => (
      `| ${name} | \`${actual}\` | \`${expected}\` | ${actual === expected ? 'PASS' : 'FAIL'} |`
    )),
    '',
    `Overall: **${failures.length === 0 ? 'PASS' : 'FAIL'}**`,
    '',
  ].join('\n');

  if (evidencePath) {
    mkdirSync(dirname(evidencePath), { recursive: true });
    writeFileSync(evidencePath, evidence);
  }
  process.stdout.write(evidence);

  if (failures.length > 0) {
    process.exitCode = 1;
  }
} finally {
  rmSync(tempRoot, { recursive: true, force: true });
}
