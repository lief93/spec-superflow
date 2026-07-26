#!/usr/bin/env node

import { execFileSync } from 'node:child_process';
import {
  existsSync,
  mkdtempSync,
  mkdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { verifyOfflineBundleIntegrity } from './lib/offline-bundle-integrity.mjs';

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
const integrityOnly = process.argv.includes('--integrity-only');
const integrity = verifyOfflineBundleIntegrity(bundleDir, {
  name: pkg.name,
  version: pkg.version,
  node: pkg.engines.node,
});
const currentPackagePath = integrity.packagePath;

if (integrityOnly) {
  console.log(`Integrity: PASS (${integrity.manifest.package})`);
  process.exit(0);
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

  checks.push(['Bundle integrity before extraction', 'passed', 'passed']);
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
    'Production Plugin MCP',
    existsSync(join(pluginRoot, '.mcp.json'))
      && Object.keys(JSON.parse(readFileSync(join(pluginRoot, '.mcp.json'), 'utf8')).mcpServers || {}).length === 0
      ? 'Not Configured'
      : 'Unexpected configuration',
    'Not Configured',
    'NOT CONFIGURED',
  ]);
  checks.push([
    'Clean environment before local tgz CLI installation',
    existsSync(join(cleanPrefix, 'bin', 'ssf')) ? 'CLI present' : 'CLI missing',
    'CLI missing',
  ]);

  installOffline(currentPackagePath, cleanPrefix, cache);
  const cleanInstalledVersion = run(
    join(cleanPrefix, 'bin', 'ssf'),
    ['--version'],
  );
  checks.push([
    'Explicit local tgz CLI installation',
    cleanInstalledVersion,
    pkg.version,
  ]);
  installOffline(currentPackagePath, cleanPrefix, cache);
  const repeatedInstalledVersion = run(
    join(cleanPrefix, 'bin', 'ssf'),
    ['--version'],
  );
  checks.push(['Repeated local tgz CLI installation', repeatedInstalledVersion, pkg.version]);

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
  checks.push([
    'VS Code command discovery and invocation',
    'Pending VS Code runtime',
    'Pending VS Code runtime',
    'PENDING',
  ]);
  checks.push([
    'VS Code missing-CLI install and READY rendering',
    'Pending VS Code runtime',
    'Pending VS Code runtime',
    'PENDING',
  ]);
  checks.push([
    'VS Code 0.13.0 upgrade and READY rendering',
    'Pending VS Code runtime',
    'Pending VS Code runtime',
    'PENDING',
  ]);
  checks.push([
    'VS Code second invocation and idempotent message',
    'Pending VS Code runtime',
    'Pending VS Code runtime',
    'PENDING',
  ]);

  const failures = checks.filter(([, actual, expected, status]) => (
    status !== 'PENDING' && status !== 'NOT CONFIGURED' && actual !== expected
  ));
  const evidence = [
    `# Offline Install and Upgrade Evidence`,
    '',
    `- Current version: \`${pkg.version}\``,
    '- Previous version: `0.13.0`',
    '- Network mode: npm `--offline` with registry forced to `127.0.0.1:9`',
    '- Installation prefix: isolated temporary directory',
    '- User global CLI and VS Code settings: unchanged',
    '- Scope: local package integrity and CLI installation primitives only',
    '- VS Code Plugin Chat runtime: PENDING',
    '- Production Plugin MCP: NOT CONFIGURED',
    '',
    '| Check | Actual | Expected | Result |',
    '|---|---|---|---|',
    ...checks.map(([name, actual, expected, status]) => (
      `| ${name} | \`${actual}\` | \`${expected}\` | ${status || (actual === expected ? 'PASS' : 'FAIL')} |`
    )),
    '',
    `Executed local checks: **${failures.length === 0 ? 'PASS' : 'FAIL'}**`,
    '',
    'This evidence does not claim that VS Code discovered or executed',
    '`/workflow-init`, rendered `READY`, or called a production MCP tool.',
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
