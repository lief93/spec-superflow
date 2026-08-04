#!/usr/bin/env node

import { spawnSync } from 'node:child_process';
import {
  chmodSync,
  copyFileSync,
  cpSync,
  existsSync,
  lstatSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  readlinkSync,
  realpathSync,
  rmSync,
  symlinkSync,
} from 'node:fs';
import { homedir, tmpdir } from 'node:os';
import { basename, delimiter, dirname, isAbsolute, join, relative } from 'node:path';
import { createInterface } from 'node:readline';
import { fileURLToPath } from 'node:url';

const SERVER_DIR = dirname(fileURLToPath(import.meta.url));
const PLUGIN_ROOT = dirname(SERVER_DIR);
const PACKAGE_PATH = join(PLUGIN_ROOT, 'package.json');
const PLUGIN_MANIFEST_PATH = join(PLUGIN_ROOT, 'plugin.json');
const CLI_SOURCE = join(PLUGIN_ROOT, 'scripts', 'spec-superflow.mjs');
const LAUNCHER_SOURCE = join(PLUGIN_ROOT, 'servers', 'spec-superflow-mcp-launcher.cmd');
const OPTIONAL_MCP_SOURCE = join(PLUGIN_ROOT, 'servers', 'token-example-mcp.mjs');
const OPTIONAL_MCP_NAME = 'spec-superflow-optional-example';
const OPTIONAL_MCP_URL_INPUT = 'spec-superflow-optional-mcp-url';
const OPTIONAL_MCP_TOKEN_INPUT = 'spec-superflow-optional-mcp-token';
const PLUGIN_HOST = process.env.SPEC_SUPERFLOW_PLUGIN_HOST ?? 'vscode';
const PLUGIN_APP_NAME = PLUGIN_HOST === 'opencode' ? 'OpenCode' : 'VS Code';

const TOOLS = [
  {
    name: 'spec_superflow_cli_status',
    description: 'Read the installed Spec Superflow CLI status without changing files or accessing the network.',
    inputSchema: {
      type: 'object',
      properties: {},
      additionalProperties: false,
    },
    annotations: {
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: false,
    },
  },
  {
    name: 'spec_superflow_install_cli',
    description: 'Used only by /workflow-init to install or upgrade the CLI from this Plugin after user confirmation.',
    inputSchema: {
      type: 'object',
      properties: {},
      additionalProperties: false,
    },
    annotations: {
      readOnlyHint: false,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: false,
    },
  },
  {
    name: 'spec_superflow_optional_mcp_status',
    description: 'Read whether the optional credentialed MCP definition is registered. It never reads credentials.',
    inputSchema: {
      type: 'object',
      properties: {},
      additionalProperties: false,
    },
    annotations: {
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: false,
    },
  },
  {
    name: 'spec_superflow_install_optional_mcp',
    description: 'Register the bundled optional MCP after user opt-in. VS Code collects URL and Token securely.',
    inputSchema: {
      type: 'object',
      properties: {},
      additionalProperties: false,
    },
    annotations: {
      readOnlyHint: false,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: false,
    },
  },
];
const AVAILABLE_TOOLS = PLUGIN_HOST === 'vscode' ? TOOLS : TOOLS.slice(0, 2);

function write(message) {
  process.stdout.write(`${JSON.stringify(message)}\n`);
}

function result(id, value) {
  write({ jsonrpc: '2.0', id, result: value });
}

function error(id, code, message) {
  write({ jsonrpc: '2.0', id, error: { code, message } });
}

function textResult(value, isError = false) {
  return {
    content: [{ type: 'text', text: JSON.stringify(value, null, 2) }],
    ...(isError ? { isError: true } : {}),
  };
}

function inside(root, candidate) {
  const path = relative(root, candidate);
  return path === '' || (!path.startsWith('..') && !isAbsolute(path));
}

function loadPlugin() {
  const root = realpathSync(PLUGIN_ROOT);
  const packagePath = realpathSync(PACKAGE_PATH);
  const manifestPath = realpathSync(PLUGIN_MANIFEST_PATH);
  const cliSource = realpathSync(CLI_SOURCE);
  const launcher = realpathSync(LAUNCHER_SOURCE);
  for (const path of [packagePath, manifestPath, cliSource, launcher]) {
    if (!inside(root, path)) throw new Error(`Plugin resource resolves outside PLUGIN_ROOT: ${path}`);
  }

  const pkg = JSON.parse(readFileSync(packagePath, 'utf8'));
  const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'));
  if (pkg.name !== 'spec-superflow') throw new Error('Plugin package name must be spec-superflow');
  if (!/^\d+\.\d+\.\d+$/.test(pkg.version ?? '')) throw new Error('Plugin package version is invalid');
  if (manifest.version !== pkg.version) throw new Error('Plugin and CLI package versions differ');
  if (pkg.bin?.ssf !== './scripts/spec-superflow.mjs') {
    throw new Error('Plugin package must expose scripts/spec-superflow.mjs as ssf');
  }
  return { root, version: pkg.version, cliSource, launcher };
}

function loadOptionalMcp() {
  const plugin = loadPlugin();
  const server = realpathSync(OPTIONAL_MCP_SOURCE);
  if (!inside(plugin.root, server)) {
    throw new Error(`Optional MCP resource resolves outside PLUGIN_ROOT: ${server}`);
  }
  return { ...plugin, server };
}

function optionalMcpDefinition() {
  const optional = loadOptionalMcp();
  return {
    name: OPTIONAL_MCP_NAME,
    type: 'stdio',
    command: optional.launcher,
    args: [optional.server],
    env: {
      SPEC_SUPERFLOW_EXAMPLE_URL: `\${input:${OPTIONAL_MCP_URL_INPUT}}`,
      SPEC_SUPERFLOW_EXAMPLE_TOKEN: `\${input:${OPTIONAL_MCP_TOKEN_INPUT}}`,
    },
    inputs: [
      {
        type: 'promptString',
        id: OPTIONAL_MCP_URL_INPUT,
        description: 'Service URL for the optional Spec Superflow MCP',
        password: false,
      },
      {
        type: 'promptString',
        id: OPTIONAL_MCP_TOKEN_INPUT,
        description: 'Token for the optional Spec Superflow MCP',
        password: false,
      },
    ],
  };
}

function executableNames(name, platform = process.platform) {
  return platform === 'win32' ? [`${name}.cmd`, `${name}.exe`, `${name}.bat`, name] : [name];
}

function findExecutable(name, env = process.env) {
  for (const entry of (env.PATH ?? '').split(delimiter).filter(Boolean)) {
    for (const candidateName of executableNames(name)) {
      const candidate = join(entry, candidateName);
      try {
        if (lstatSync(candidate).isFile() || lstatSync(candidate).isSymbolicLink()) {
          return candidate;
        }
      } catch {
        // Continue searching PATH.
      }
    }
  }
  return null;
}

function run(command, args, env = process.env) {
  const execution = spawnSync(command, args, {
    encoding: 'utf8',
    env,
    windowsHide: true,
    maxBuffer: 10 * 1024 * 1024,
  });
  return {
    exitCode: execution.status ?? 1,
    stdout: execution.stdout?.trim() ?? '',
    stderr: execution.stderr?.trim() ?? execution.error?.message ?? '',
  };
}

function vscodeUserMcpPath(env = process.env) {
  if (env.SPEC_SUPERFLOW_VSCODE_USER_MCP) {
    return isAbsolute(env.SPEC_SUPERFLOW_VSCODE_USER_MCP)
      ? env.SPEC_SUPERFLOW_VSCODE_USER_MCP
      : null;
  }
  const home = env.HOME || env.USERPROFILE || homedir();
  if (process.platform === 'darwin') {
    return join(home, 'Library', 'Application Support', 'Code', 'User', 'mcp.json');
  }
  if (process.platform === 'win32') {
    return env.APPDATA ? join(env.APPDATA, 'Code', 'User', 'mcp.json') : null;
  }
  const config = env.XDG_CONFIG_HOME || join(home, '.config');
  return join(config, 'Code', 'User', 'mcp.json');
}

function optionalMcpStatus(env = process.env) {
  const configPath = vscodeUserMcpPath(env);
  const base = {
    optional: true,
    workflowBlocking: false,
    configPath,
  };
  if (!configPath) {
    return {
      ...base,
      status: 'unknown',
      configured: false,
      reason: 'vscode-user-mcp-path-unavailable',
      requiredAction: 'offer-optional-mcp-configuration',
    };
  }
  if (!existsSync(configPath)) {
    return {
      ...base,
      status: 'not-configured',
      configured: false,
      reason: null,
      requiredAction: 'offer-optional-mcp-configuration',
    };
  }

  try {
    const config = JSON.parse(readFileSync(configPath, 'utf8'));
    const definition = optionalMcpDefinition();
    const server = config.servers?.[OPTIONAL_MCP_NAME];
    const inputIds = new Set((config.inputs ?? []).map(input => input.id));
    const configured = Boolean(
      server
      && server.type === definition.type
      && server.command === definition.command
      && server.args?.[0] === definition.args[0]
      && server.env?.SPEC_SUPERFLOW_EXAMPLE_URL === definition.env.SPEC_SUPERFLOW_EXAMPLE_URL
      && server.env?.SPEC_SUPERFLOW_EXAMPLE_TOKEN === definition.env.SPEC_SUPERFLOW_EXAMPLE_TOKEN
      && definition.inputs.every(input => inputIds.has(input.id)),
    );
    return {
      ...base,
      status: configured ? 'configured' : 'outdated',
      configured,
      reason: configured ? null : 'optional-mcp-definition-mismatch',
      requiredAction: configured
        ? 'start-or-use-optional-mcp'
        : 'offer-optional-mcp-configuration',
    };
  } catch (cause) {
    return {
      ...base,
      status: 'unknown',
      configured: false,
      reason: 'vscode-user-mcp-config-unreadable',
      requiredAction: 'offer-optional-mcp-configuration',
      error: cause.message,
    };
  }
}

function vscodeCli(env = process.env, runtime = {}) {
  const platform = runtime.platform ?? process.platform;
  const execPath = runtime.execPath ?? process.execPath;
  const override = env.SPEC_SUPERFLOW_VSCODE_CLI;
  if (override) {
    if (!isAbsolute(override) || !existsSync(override)) return null;
    return realpathSync(override);
  }

  const fromPath = findExecutable('code', env);
  if (fromPath) return realpathSync(fromPath);

  if (platform === 'darwin') {
    const candidates = [join(
      dirname(dirname(execPath)),
      'Resources',
      'app',
      'bin',
      'code',
    )];
    const applicationDirs = runtime.applicationDirs ?? [
      join(env.HOME || homedir(), 'Applications'),
      '/Applications',
    ];
    for (const applications of applicationDirs) {
      candidates.push(
        join(applications, 'Visual Studio Code.app', 'Contents', 'Resources', 'app', 'bin', 'code'),
        join(
          applications,
          'Visual Studio Code - Insiders.app',
          'Contents',
          'Resources',
          'app',
          'bin',
          'code-insiders',
        ),
      );
    }
    for (const candidate of candidates) {
      if (existsSync(candidate)) return realpathSync(candidate);
    }
  }
  if (platform === 'win32' && /^code(?: - insiders)?\.exe$/i.test(basename(execPath))) {
    return realpathSync(execPath);
  }
  if (platform === 'linux' && /^code(?:-insiders)?$/i.test(basename(execPath))) {
    return realpathSync(execPath);
  }
  return null;
}

function installOptionalMcp(arguments_, env = process.env) {
  if (Object.keys(arguments_ ?? {}).length > 0) {
    return {
      status: 'blocked',
      configured: false,
      optional: true,
      workflowBlocking: false,
      reason: 'invalid-optional-mcp-request',
      error: 'spec_superflow_install_optional_mcp does not accept arguments',
    };
  }

  const before = optionalMcpStatus(env);
  if (before.configured) {
    return {
      ...before,
      installed: false,
      requiresCredentialPrompt: false,
    };
  }

  let definition;
  try {
    definition = optionalMcpDefinition();
  } catch (cause) {
    return {
      ...before,
      status: 'blocked',
      configured: false,
      reason: 'invalid-optional-mcp-package',
      installed: false,
      requiresCredentialPrompt: false,
      error: cause.message,
    };
  }

  const code = vscodeCli(env);
  if (!code) {
    return {
      ...before,
      status: 'blocked',
      configured: false,
      reason: 'vscode-cli-unavailable',
      installed: false,
      requiresCredentialPrompt: false,
      recovery: 'Open VS Code from a standard installation and run workflow-init again.',
    };
  }

  const childEnv = { ...env };
  delete childEnv.ELECTRON_RUN_AS_NODE;
  const registration = run(code, ['--add-mcp', JSON.stringify(definition)], childEnv);
  if (registration.exitCode !== 0) {
    return {
      ...before,
      status: 'blocked',
      configured: false,
      reason: 'vscode-mcp-registration-failed',
      installed: false,
      requiresCredentialPrompt: false,
      recovery: 'Resolve the VS Code MCP configuration error, then retry optional MCP setup.',
      error: registration.stderr || registration.stdout,
    };
  }

  const after = optionalMcpStatus(env);
  if (!after.configured) {
    return {
      ...after,
      status: 'blocked',
      configured: false,
      reason: 'vscode-mcp-registration-not-detected',
      installed: false,
      requiresCredentialPrompt: false,
      recovery: 'Open MCP: Open User Configuration, verify the generated definition, then retry.',
    };
  }
  return {
    ...after,
    installed: true,
    requiresCredentialPrompt: true,
    requiredAction: 'complete-vscode-url-token-prompts',
  };
}

function readCli(executable, env = process.env) {
  if (!executable) return { available: false, path: null, realPath: null, version: null };
  let realPath = null;
  try {
    realPath = realpathSync(executable);
  } catch {
    return { available: false, path: executable, realPath: null, version: null };
  }
  const execution = run(executable, ['--version'], env);
  const version = execution.exitCode === 0 && /^\d+\.\d+\.\d+$/.test(execution.stdout)
    ? execution.stdout
    : null;
  return {
    available: execution.exitCode === 0,
    path: executable,
    realPath,
    version,
    exitCode: execution.exitCode,
    stderr: execution.stderr,
  };
}

function readNode(env = process.env) {
  const path = findExecutable('node', env);
  if (!path) return { available: false, path: null, version: null };
  const execution = run(path, ['--version'], env);
  return {
    available: execution.exitCode === 0,
    path,
    version: execution.exitCode === 0 ? execution.stdout : null,
    exitCode: execution.exitCode,
    stderr: execution.stderr,
  };
}

function cliRecovery(reason, { bin, previousCli } = {}) {
  switch (reason) {
    case 'invalid-install-request':
      return 'Call spec_superflow_install_cli without arguments.';
    case 'invalid-plugin-package':
      return `Repair the Plugin installation, restart ${PLUGIN_APP_NAME}, and run workflow-init again.`;
    case 'node-missing':
      return `Install Node.js, add it to PATH, restart ${PLUGIN_APP_NAME}, and run workflow-init again.`;
    case 'npm-missing':
      return PLUGIN_HOST === 'opencode'
        ? 'Install Node.js with npm, restart OpenCode, and run workflow-init again.'
        : 'Install Node.js with npm, then run workflow-init again.';
    case 'cli-version-unreadable':
      return 'Repair the global ssf CLI, then run workflow-init again.';
    case 'npm-prefix-unavailable':
      return 'Fix the npm global prefix, then run workflow-init again.';
    case 'npm-install-failed':
      return 'The previous CLI was restored. Resolve the npm permission or prefix error, then retry.';
    case 'installed-cli-not-on-path':
      return `Add ${bin} to the front of PATH, restart ${PLUGIN_APP_NAME}, and run workflow-init again.`;
    case 'version-mismatch-after-install':
      return previousCli
        ? 'The previous CLI was restored. Verify the Plugin package version and retry.'
        : 'The incomplete CLI installation was removed. Verify the Plugin package and retry.';
    case 'install-exception':
      return 'The previous CLI was restored. Resolve the reported error, then retry.';
    default:
      return 'Resolve the reported CLI error, then run workflow-init again.';
  }
}

function cliStatus(env = process.env) {
  const node = readNode(env);
  let plugin;
  try {
    plugin = loadPlugin();
  } catch (cause) {
    return {
      status: 'blocked',
      ready: false,
      installRequired: false,
      reason: 'invalid-plugin-package',
      requiredAction: 'repair-plugin-installation',
      error: cause.message,
      node,
      recovery: cliRecovery('invalid-plugin-package'),
    };
  }

  const npmPath = findExecutable('npm', env);
  const cli = readCli(findExecutable('ssf', env), env);
  const prefixResult = npmPath ? run(npmPath, ['prefix', '-g'], env) : null;
  const npmPrefix = prefixResult?.exitCode === 0 && isAbsolute(prefixResult.stdout)
    ? prefixResult.stdout
    : null;
  const globalCliPath = npmPrefix
    ? join(globalBin(npmPrefix), executableNames('ssf')[0])
    : null;
  const installedCli = readCli(globalCliPath, env);
  const installedCliReady = installedCli.version === plugin.version;
  const cliReady = cli.version === plugin.version
    && cli.realPath === installedCli.realPath;
  const installedCliOffPath = installedCliReady && !cliReady;
  const ready = node.available
    && Boolean(npmPath)
    && Boolean(npmPrefix)
    && installedCliReady
    && cliReady;
  let status = 'ready';
  let reason = null;
  if (!node.available) {
    status = 'blocked';
    reason = 'node-missing';
  } else if (!npmPath) {
    status = 'blocked';
    reason = 'npm-missing';
  } else if (!npmPrefix) {
    status = 'blocked';
    reason = 'npm-prefix-unavailable';
  } else if (!installedCli.available) {
    status = 'missing';
    reason = 'cli-missing';
  } else if (!installedCli.version) {
    status = 'blocked';
    reason = 'cli-version-unreadable';
  } else if (!installedCliReady) {
    status = 'mismatch';
    reason = 'cli-version-mismatch';
  } else if (installedCliOffPath) {
    status = 'blocked';
    reason = 'installed-cli-not-on-path';
  }

  return {
    status,
    ready,
    installRequired: reason === 'cli-missing' || reason === 'cli-version-mismatch',
    reason,
    requiredAction: ready
      ? 'verify-with-ssf-version'
      : reason === 'installed-cli-not-on-path'
        ? 'add-cli-to-path'
      : reason === 'cli-missing' || reason === 'cli-version-mismatch'
        ? 'request-install-confirmation'
        : reason === 'node-missing'
          ? 'install-node'
          : reason === 'npm-missing'
            ? 'install-node-with-npm'
            : 'repair-cli-installation',
    pluginVersion: plugin.version,
    pluginRoot: plugin.root,
    node,
    npm: { available: Boolean(npmPath), path: npmPath, prefix: npmPrefix },
    cli,
    installedCli,
    ...(status === 'blocked' ? {
      recovery: cliRecovery(reason, { bin: npmPrefix ? globalBin(npmPrefix) : null }),
    } : {}),
  };
}

function globalBin(prefix) {
  return process.platform === 'win32' ? prefix : join(prefix, 'bin');
}

function globalPackage(prefix) {
  return process.platform === 'win32'
    ? join(prefix, 'node_modules', 'spec-superflow')
    : join(prefix, 'lib', 'node_modules', 'spec-superflow');
}

function snapshotPath(path, backupRoot, name) {
  if (!existsSync(path)) return { path, existed: false };
  const stat = lstatSync(path);
  if (stat.isSymbolicLink()) {
    return { path, existed: true, type: 'symlink', target: readlinkSync(path) };
  }
  const backup = join(backupRoot, name);
  if (stat.isDirectory()) {
    cpSync(path, backup, { recursive: true, dereference: false });
    return { path, existed: true, type: 'directory', backup };
  }
  copyFileSync(path, backup);
  return { path, existed: true, type: 'file', backup, mode: stat.mode };
}

function restorePath(snapshot) {
  rmSync(snapshot.path, { recursive: true, force: true });
  if (!snapshot.existed) return;
  mkdirSync(dirname(snapshot.path), { recursive: true });
  if (snapshot.type === 'symlink') {
    symlinkSync(snapshot.target, snapshot.path);
  } else if (snapshot.type === 'directory') {
    cpSync(snapshot.backup, snapshot.path, { recursive: true, dereference: false });
  } else {
    copyFileSync(snapshot.backup, snapshot.path);
    chmodSync(snapshot.path, snapshot.mode);
  }
}

function installCli(arguments_, env = process.env) {
  if (Object.keys(arguments_ ?? {}).length > 0) {
    return {
      status: 'blocked',
      reason: 'invalid-install-request',
      error: 'spec_superflow_install_cli does not accept arguments',
      recovery: cliRecovery('invalid-install-request'),
    };
  }

  const before = cliStatus(env);
  if (before.ready) {
    return { ...before, installed: false, upgraded: false, rolledBack: false };
  }
  if (before.reason === 'invalid-plugin-package') {
    return { ...before, installed: false, upgraded: false, rolledBack: false };
  }
  if (before.reason === 'installed-cli-not-on-path') {
    return { ...before, installed: false, upgraded: false, rolledBack: false };
  }
  if (!before.node?.available) {
    return {
      ...before,
      status: 'blocked',
      reason: 'node-missing',
      installed: false,
      upgraded: false,
      rolledBack: false,
      recovery: cliRecovery('node-missing'),
    };
  }
  if (!before.npm?.available) {
    return {
      ...before,
      status: 'blocked',
      reason: 'npm-missing',
      installed: false,
      upgraded: false,
      rolledBack: false,
      recovery: cliRecovery('npm-missing'),
    };
  }

  const prefixResult = run(before.npm.path, ['prefix', '-g'], env);
  if (prefixResult.exitCode !== 0 || !isAbsolute(prefixResult.stdout)) {
    return {
      ...before,
      status: 'blocked',
      ready: false,
      reason: 'npm-prefix-unavailable',
      installed: false,
      upgraded: false,
      rolledBack: false,
      recovery: cliRecovery('npm-prefix-unavailable'),
      error: prefixResult.stderr || prefixResult.stdout,
    };
  }

  const prefix = prefixResult.stdout;
  const bin = globalBin(prefix);
  const packagePath = globalPackage(prefix);
  const aliases = executableNames('ssf').concat(executableNames('spec-superflow'))
    .map(name => join(bin, name));
  const backupRoot = mkdtempSync(join(tmpdir(), 'spec-superflow-cli-backup-'));
  const snapshots = [
    snapshotPath(packagePath, backupRoot, 'package'),
    ...aliases.map((path, index) => snapshotPath(path, backupRoot, `bin-${index}`)),
  ];
  const rollback = () => {
    for (const snapshot of snapshots) restorePath(snapshot);
  };

  try {
    const installation = run(
      before.npm.path,
      ['install', '-g', '--install-links=true', '--prefix', prefix, loadPlugin().root],
      env,
    );
    if (installation.exitCode !== 0) {
      rollback();
      return {
        ...before,
        status: 'blocked',
        ready: false,
        reason: 'npm-install-failed',
        installed: false,
        upgraded: false,
        rolledBack: true,
        previousCli: before.installedCli,
        recovery: cliRecovery('npm-install-failed'),
        error: installation.stderr || installation.stdout,
      };
    }

    const after = cliStatus(env);
    if (after.ready) {
      return {
        ...after,
        installed: true,
        upgraded: Boolean(before.installedCli?.available),
        rolledBack: false,
        previousCli: before.installedCli,
      };
    }

    const installedPath = join(bin, executableNames('ssf')[0]);
    const installedCli = readCli(installedPath, env);
    if (
      installedCli.version === before.pluginVersion
      && after.reason === 'installed-cli-not-on-path'
    ) {
      return {
        ...after,
        status: 'blocked',
        ready: false,
        reason: 'installed-cli-not-on-path',
        installed: true,
        upgraded: Boolean(before.installedCli?.available),
        rolledBack: false,
        installedCli,
        previousCli: before.installedCli,
        recovery: cliRecovery('installed-cli-not-on-path', { bin }),
      };
    }

    rollback();
    const restored = cliStatus(env);
    return {
      ...restored,
      status: 'blocked',
      ready: false,
      reason: 'version-mismatch-after-install',
      installed: false,
      upgraded: false,
      rolledBack: true,
      previousCli: before.installedCli,
      attemptedCli: installedCli,
      recovery: cliRecovery('version-mismatch-after-install', {
        previousCli: before.installedCli?.available,
      }),
    };
  } catch (cause) {
    rollback();
    return {
      ...before,
      status: 'blocked',
      ready: false,
      reason: 'install-exception',
      installed: false,
      upgraded: false,
      rolledBack: true,
      previousCli: before.installedCli,
      recovery: cliRecovery('install-exception'),
      error: cause.message,
    };
  } finally {
    rmSync(backupRoot, { recursive: true, force: true });
  }
}

function handle(message) {
  if (!message || message.jsonrpc !== '2.0') return;

  if (message.method === 'initialize') {
    let version = 'unknown';
    try {
      version = loadPlugin().version;
    } catch {
      // Status reports the concrete package failure.
    }
    result(message.id, {
      protocolVersion: message.params?.protocolVersion ?? '2025-06-18',
      capabilities: { tools: { listChanged: false } },
      serverInfo: { name: 'spec-superflow-bootstrap', version },
    });
    return;
  }
  if (message.method === 'ping') {
    result(message.id, {});
    return;
  }
  if (message.method === 'tools/list') {
    result(message.id, { tools: AVAILABLE_TOOLS });
    return;
  }
  if (message.method === 'tools/call') {
    const name = message.params?.name;
    const args = message.params?.arguments ?? {};
    if (name === 'spec_superflow_cli_status') {
      result(message.id, textResult(cliStatus()));
    } else if (name === 'spec_superflow_install_cli') {
      const installation = installCli(args);
      result(message.id, textResult(installation, installation.status === 'blocked'));
    } else if (PLUGIN_HOST === 'vscode' && name === 'spec_superflow_optional_mcp_status') {
      result(message.id, textResult(optionalMcpStatus()));
    } else if (PLUGIN_HOST === 'vscode' && name === 'spec_superflow_install_optional_mcp') {
      const installation = installOptionalMcp(args);
      result(message.id, textResult(installation, installation.status === 'blocked'));
    } else {
      error(message.id, -32602, `Unknown tool: ${name ?? '<missing>'}`);
    }
    return;
  }
  if (message.id !== undefined) {
    error(message.id, -32601, `Method not found: ${message.method}`);
  }
}

const input = createInterface({ input: process.stdin, crlfDelay: Infinity });
input.on('line', line => {
  if (!line.trim()) return;
  try {
    handle(JSON.parse(line));
  } catch (cause) {
    process.stderr.write(`Invalid MCP message: ${cause.message}\n`);
  }
});

export {
  cliStatus,
  findExecutable,
  installCli,
  installOptionalMcp,
  loadPlugin,
  optionalMcpDefinition,
  optionalMcpStatus,
  vscodeCli,
};
