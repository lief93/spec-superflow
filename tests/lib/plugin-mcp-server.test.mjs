import assert from 'node:assert/strict';
import { spawn, spawnSync } from 'node:child_process';
import {
  chmodSync,
  cpSync,
  existsSync,
  lstatSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  readlinkSync,
  realpathSync,
  readdirSync,
  rmSync,
  statSync,
  symlinkSync,
  writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { createInterface } from 'node:readline';
import { afterEach, describe, it } from 'node:test';
import { pathToFileURL } from 'node:url';

const ROOT = process.cwd();
const roots = [];

function makeRoot(prefix) {
  const root = mkdtempSync(join(tmpdir(), prefix));
  roots.push(root);
  return root;
}

function writeExecutable(path, source) {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, source);
  chmodSync(path, 0o755);
}

function fakeNode(path) {
  mkdirSync(dirname(path), { recursive: true });
  symlinkSync(process.execPath, path);
}

function copyPluginRoot(parent, name = 'Spec Superflow Plugin') {
  const root = join(parent, name);
  mkdirSync(join(root, 'servers'), { recursive: true });
  mkdirSync(join(root, 'scripts'), { recursive: true });
  cpSync(
    join(ROOT, 'servers/spec-superflow-mcp-launcher.cmd'),
    join(root, 'servers/spec-superflow-mcp-launcher.cmd'),
  );
  cpSync(join(ROOT, 'servers/spec-superflow-mcp.mjs'), join(root, 'servers/spec-superflow-mcp.mjs'));
  cpSync(join(ROOT, 'servers/token-example-mcp.mjs'), join(root, 'servers/token-example-mcp.mjs'));
  cpSync(join(ROOT, 'scripts/spec-superflow.mjs'), join(root, 'scripts/spec-superflow.mjs'));
  cpSync(join(ROOT, 'package.json'), join(root, 'package.json'));
  cpSync(join(ROOT, 'plugin.json'), join(root, 'plugin.json'));
  return root;
}

function fakeNpm(path) {
  fakeNode(join(dirname(path), 'node'));
  writeExecutable(
    path,
    `#!${process.execPath}
import { chmodSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
const args = process.argv.slice(2);
if (process.env.FAKE_NPM_LOG) {
  writeFileSync(process.env.FAKE_NPM_LOG, JSON.stringify(args) + '\\n', { flag: 'a' });
}
if (args[0] === 'prefix' && args[1] === '-g') {
  console.log(process.env.FAKE_NPM_PREFIX);
  process.exit(0);
}
if (args[0] === 'install') {
  const prefix = args[args.indexOf('--prefix') + 1];
  const bin = process.platform === 'win32' ? join(prefix, 'ssf.cmd') : join(prefix, 'bin', 'ssf');
  if (process.env.FAKE_NPM_DELETE_EXISTING === '1' && existsSync(bin)) rmSync(bin, { force: true });
  if (process.env.FAKE_NPM_MODE === 'fail') {
    console.error('EACCES simulated global install failure');
    process.exit(13);
  }
  mkdirSync(dirname(bin), { recursive: true });
  const version = process.env.FAKE_INSTALL_VERSION || '0.14.0';
  writeFileSync(bin, '#!${process.execPath}\\nconsole.log(' + JSON.stringify(version) + ')\\n');
  chmodSync(bin, 0o755);
  process.exit(0);
}
console.error('unsupported fake npm call: ' + args.join(' '));
process.exit(2);
`,
  );
}

function fakeSsf(path, version, { symlinkTarget } = {}) {
  if (symlinkTarget) {
    writeExecutable(symlinkTarget, `#!${process.execPath}\nconsole.log(${JSON.stringify(version)})\n`);
    mkdirSync(dirname(path), { recursive: true });
    writeFileSync(path, readFileSync(symlinkTarget));
    chmodSync(path, 0o755);
    return;
  }
  writeExecutable(path, `#!${process.execPath}\nconsole.log(${JSON.stringify(version)})\n`);
}

function fakeCode(path) {
  writeExecutable(
    path,
    `#!${process.execPath}
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname } from 'node:path';
const args = process.argv.slice(2);
if (process.env.FAKE_CODE_LOG) {
  writeFileSync(process.env.FAKE_CODE_LOG, JSON.stringify(args) + '\\n', { flag: 'a' });
}
if (process.env.FAKE_CODE_MODE === 'fail') {
  console.error('simulated VS Code MCP registration failure');
  process.exit(17);
}
if (args[0] !== '--add-mcp' || !args[1]) {
  console.error('unsupported fake code call: ' + args.join(' '));
  process.exit(2);
}
const definition = JSON.parse(args[1]);
const target = process.env.SPEC_SUPERFLOW_VSCODE_USER_MCP;
const existing = existsSync(target)
  ? JSON.parse(readFileSync(target, 'utf8'))
  : { servers: {}, inputs: [] };
existing.servers ??= {};
existing.inputs ??= [];
existing.servers[definition.name] = Object.fromEntries(
  Object.entries(definition).filter(([key]) => !['name', 'inputs'].includes(key)),
);
const ids = new Set(existing.inputs.map(input => input.id));
for (const input of definition.inputs ?? []) {
  if (!ids.has(input.id)) existing.inputs.push(input);
}
mkdirSync(dirname(target), { recursive: true });
writeFileSync(target, JSON.stringify(existing, null, 2));
console.log('Added MCP servers: ' + definition.name);
`,
  );
}

function treeSnapshot(root) {
  if (!existsSync(root)) return [];
  const walk = path => readdirSync(path, { withFileTypes: true }).flatMap(entry => {
    const child = join(path, entry.name);
    if (entry.isDirectory()) return walk(child);
    const stat = lstatSync(child);
    return [{
      path: child.slice(root.length + 1),
      mode: stat.mode,
      size: stat.size,
      link: stat.isSymbolicLink() ? readlinkSync(child) : null,
      content: stat.isSymbolicLink() ? null : readFileSync(child, 'hex'),
    }];
  });
  return walk(root);
}

function startClient({ pluginRoot = ROOT, env = {} } = {}) {
  const child = spawn(process.execPath, [join(pluginRoot, 'servers/spec-superflow-mcp.mjs')], {
    cwd: pluginRoot,
    env: { ...process.env, ...env },
    stdio: ['pipe', 'pipe', 'pipe'],
  });
  const pending = new Map();
  const output = createInterface({ input: child.stdout, crlfDelay: Infinity });
  let stderr = '';
  child.stderr.on('data', chunk => { stderr += chunk; });
  output.on('line', line => {
    const message = JSON.parse(line);
    pending.get(message.id)?.(message);
    pending.delete(message.id);
  });

  return {
    request(id, method, params = {}) {
      return new Promise((resolve, reject) => {
        const timer = setTimeout(() => reject(new Error(`MCP timeout: ${stderr}`)), 5000);
        pending.set(id, message => {
          clearTimeout(timer);
          resolve(message);
        });
        child.stdin.write(`${JSON.stringify({ jsonrpc: '2.0', id, method, params })}\n`);
      });
    },
    close() {
      output.close();
      child.kill();
    },
  };
}

function parseTool(call) {
  return JSON.parse(call.result.content[0].text);
}

afterEach(() => {
  while (roots.length > 0) rmSync(roots.pop(), { recursive: true, force: true });
});

describe('production Plugin bootstrap MCP', () => {
  it('reports URL and token evidence without revealing credential values', () => {
    const url = 'https://service.example/mcp';
    const token = 'visible-test-token';
    const serverUrl = pathToFileURL(join(ROOT, 'servers/token-example-mcp.mjs')).href;
    const probe = spawnSync(
      process.execPath,
      [
        '--input-type=module',
        '--eval',
        [
          `const { tokenStatus } = await import(${JSON.stringify(serverUrl)});`,
          'process.stdout.write(tokenStatus({}).content[0].text);',
          'process.exit(0);',
        ].join('\n'),
      ],
      {
        encoding: 'utf8',
        env: {
          ...process.env,
          SPEC_SUPERFLOW_EXAMPLE_URL: url,
          SPEC_SUPERFLOW_EXAMPLE_TOKEN: token,
        },
      },
    );

    assert.equal(probe.status, 0, probe.stderr);
    const status = JSON.parse(probe.stdout);
    assert.equal(status.configured, true);
    assert.equal(status.urlLength, url.length);
    assert.equal(status.tokenLength, token.length);
    assert.equal(status.tokenFingerprint.length, 12);
    assert.doesNotMatch(probe.stdout, new RegExp(url.replaceAll('.', '\\.')));
    assert.doesNotMatch(probe.stdout, new RegExp(token));
  });

  it('launches with a login-shell Node when the VS Code process PATH has no Node', {
    skip: process.platform === 'win32',
  }, () => {
    const sandbox = makeRoot('ssf-mcp-launcher-');
    const loginShell = join(sandbox, 'fake login shell');
    writeExecutable(
      loginShell,
      `#!${process.execPath}
import { spawnSync } from 'node:child_process';
console.log('login-shell-startup-noise');
const child = spawnSync(process.execPath, process.argv.slice(5), {
  stdio: ['inherit', 3, 'inherit'],
});
process.exit(child.status ?? 1);
`,
    );

    const launched = spawnSync(
      join(ROOT, 'servers', 'spec-superflow-mcp-launcher.cmd'),
      ['-e', 'console.log("launcher-ready")'],
      {
        encoding: 'utf8',
        env: {
          HOME: sandbox,
          PATH: '',
          SHELL: loginShell,
        },
      },
    );

    assert.equal(launched.status, 0, launched.stderr);
    assert.equal(launched.stdout.trim(), 'launcher-ready');
    assert.match(launched.stderr, /login-shell-startup-noise/);
  });

  it('uses the Plugin host name when the launcher cannot find Node', {
    skip: process.platform === 'win32',
  }, () => {
    for (const [host, expected] of [
      ['opencode', 'OpenCode'],
      ['vscode', 'VS Code'],
    ]) {
      const launched = spawnSync(
        join(ROOT, 'servers', 'spec-superflow-mcp-launcher.cmd'),
        [],
        {
          encoding: 'utf8',
          env: {
            HOME: makeRoot(`ssf-launcher-${host}-`),
            PATH: '',
            SHELL: '',
            SPEC_SUPERFLOW_PLUGIN_HOST: host,
          },
        },
      );
      assert.equal(launched.status, 127);
      assert.match(launched.stderr, new RegExp(`restart ${expected.replace(' ', '\\s')}`));
      if (host === 'opencode') assert.doesNotMatch(launched.stderr, /VS Code/);
    }
  });

  it('exposes CLI bootstrap and optional MCP setup tools', async () => {
    const client = startClient();
    try {
      const initialized = await client.request(1, 'initialize', {
        protocolVersion: '2025-06-18',
        capabilities: {},
        clientInfo: { name: 'spec-superflow-test', version: '1.0.0' },
      });
      assert.equal(initialized.result.serverInfo.name, 'spec-superflow-bootstrap');

      const tools = await client.request(2, 'tools/list');
      assert.deepEqual(
        tools.result.tools.map(tool => tool.name),
        [
          'spec_superflow_cli_status',
          'spec_superflow_install_cli',
          'spec_superflow_optional_mcp_status',
          'spec_superflow_install_optional_mcp',
        ],
      );
      assert.deepEqual(tools.result.tools[0].annotations, {
        readOnlyHint: true,
        destructiveHint: false,
        idempotentHint: true,
        openWorldHint: false,
      });
      assert.deepEqual(tools.result.tools[1].inputSchema.properties, {});
      assert.deepEqual(tools.result.tools[1].annotations, {
        readOnlyHint: false,
        destructiveHint: false,
        idempotentHint: true,
        openWorldHint: false,
      });
      assert.equal(tools.result.tools[2].annotations.readOnlyHint, true);
      assert.deepEqual(tools.result.tools[3].inputSchema.properties, {});
      assert.deepEqual(tools.result.tools[3].annotations, {
        readOnlyHint: false,
        destructiveHint: false,
        idempotentHint: true,
        openWorldHint: false,
      });

      const removed = await client.request(3, 'tools/call', {
        name: 'spec_superflow_run',
        arguments: { workspace: ROOT, args: ['--version'] },
      });
      assert.equal(removed.error.code, -32602);
    } finally {
      client.close();
    }
  });

  it('exposes only CLI bootstrap tools to the OpenCode host', async () => {
    const client = startClient({
      env: {
        SPEC_SUPERFLOW_PLUGIN_HOST: 'opencode',
      },
    });
    try {
      const tools = await client.request(1, 'tools/list');
      assert.deepEqual(
        tools.result.tools.map(tool => tool.name),
        [
          'spec_superflow_cli_status',
          'spec_superflow_install_cli',
        ],
      );

      for (const name of [
        'spec_superflow_run',
        'spec_superflow_optional_mcp_status',
        'spec_superflow_install_optional_mcp',
      ]) {
        const unavailable = await client.request(2, 'tools/call', {
          name,
          arguments: {},
        });
        assert.equal(unavailable.error.code, -32602, name);
      }
    } finally {
      client.close();
    }
  });

  it('reports an absent optional MCP without changing files or blocking the workflow', async () => {
    const sandbox = makeRoot('ssf-optional-mcp-status-');
    const pluginRoot = copyPluginRoot(sandbox);
    const userMcp = join(sandbox, 'user data', 'mcp.json');
    const before = treeSnapshot(sandbox);
    const client = startClient({
      pluginRoot,
      env: {
        SPEC_SUPERFLOW_VSCODE_USER_MCP: userMcp,
      },
    });

    try {
      const status = parseTool(await client.request(1, 'tools/call', {
        name: 'spec_superflow_optional_mcp_status',
        arguments: {},
      }));
      assert.equal(status.status, 'not-configured');
      assert.equal(status.configured, false);
      assert.equal(status.optional, true);
      assert.equal(status.workflowBlocking, false);
      assert.equal(status.requiredAction, 'offer-optional-mcp-configuration');
      assert.deepEqual(treeSnapshot(sandbox), before);
    } finally {
      client.close();
    }
  });

  it('registers the bundled credentialed MCP through VS Code without receiving secrets', async () => {
    const sandbox = makeRoot('ssf-optional-mcp-install-');
    const pluginRoot = copyPluginRoot(sandbox, 'Plugin With Spaces');
    const userMcp = join(sandbox, 'user data', 'mcp.json');
    const code = join(sandbox, 'VS Code CLI', 'code');
    const log = join(sandbox, 'code.log');
    fakeCode(code);
    const client = startClient({
      pluginRoot,
      env: {
        SPEC_SUPERFLOW_VSCODE_CLI: code,
        SPEC_SUPERFLOW_VSCODE_USER_MCP: userMcp,
        FAKE_CODE_LOG: log,
      },
    });

    try {
      const installed = parseTool(await client.request(1, 'tools/call', {
        name: 'spec_superflow_install_optional_mcp',
        arguments: {},
      }));
      assert.equal(installed.status, 'configured');
      assert.equal(installed.configured, true);
      assert.equal(installed.optional, true);
      assert.equal(installed.workflowBlocking, false);
      assert.equal(installed.requiresCredentialPrompt, true);

      const config = JSON.parse(readFileSync(userMcp, 'utf8'));
      const server = config.servers['spec-superflow-optional-example'];
      const declared = new Set(config.inputs.map(input => input.id));
      const referenced = [...JSON.stringify(server).matchAll(/\$\{input:([^}]+)\}/g)]
        .map(match => match[1]);
      assert.deepEqual(server, {
        type: 'stdio',
        command: realpathSync(join(pluginRoot, 'servers', 'spec-superflow-mcp-launcher.cmd')),
        args: [realpathSync(join(pluginRoot, 'servers', 'token-example-mcp.mjs'))],
        env: {
          SPEC_SUPERFLOW_EXAMPLE_URL: '${input:spec-superflow-optional-mcp-url}',
          SPEC_SUPERFLOW_EXAMPLE_TOKEN: '${input:spec-superflow-optional-mcp-token}',
        },
      });
      assert.deepEqual(config.inputs, [
        {
          type: 'promptString',
          id: 'spec-superflow-optional-mcp-url',
          description: 'Service URL for the optional Spec Superflow MCP',
          password: false,
        },
        {
          type: 'promptString',
          id: 'spec-superflow-optional-mcp-token',
          description: 'Token for the optional Spec Superflow MCP',
          password: false,
        },
      ]);
      assert.notEqual(referenced.length, 0);
      for (const id of referenced) assert.equal(declared.has(id), true);
      assert.doesNotMatch(readFileSync(userMcp, 'utf8'), /actual-token|https:\/\/service\.example/);

      const second = parseTool(await client.request(2, 'tools/call', {
        name: 'spec_superflow_install_optional_mcp',
        arguments: {},
      }));
      assert.equal(second.status, 'configured');
      assert.equal(second.installed, false);
      assert.equal(readFileSync(log, 'utf8').trim().split('\n').length, 1);
    } finally {
      client.close();
    }
  });

  it('finds the VS Code CLI in a macOS app bundle when GUI PATH omits code', () => {
    const sandbox = makeRoot('ssf-vscode-gui-path-');
    const applications = join(sandbox, 'Applications');
    const code = join(
      applications,
      'Visual Studio Code.app',
      'Contents',
      'Resources',
      'app',
      'bin',
      'code',
    );
    fakeCode(code);

    const serverUrl = pathToFileURL(join(ROOT, 'servers/spec-superflow-mcp.mjs')).href;
    const probe = spawnSync(
      process.execPath,
      [
        '--input-type=module',
        '--eval',
        [
          `const { vscodeCli } = await import(${JSON.stringify(serverUrl)});`,
          `const resolved = vscodeCli({ PATH: '' }, {`,
          `  platform: 'darwin',`,
          `  execPath: ${JSON.stringify(join(sandbox, 'node', 'bin', 'node'))},`,
          `  applicationDirs: [${JSON.stringify(applications)}],`,
          `});`,
          `process.stdout.write(resolved ?? '');`,
        ].join('\n'),
      ],
      { encoding: 'utf8' },
    );

    assert.equal(probe.status, 0, probe.stderr);
    assert.equal(probe.stdout, realpathSync(code));
  });

  it('rejects URL, token, registry, package, and path arguments for optional MCP setup', async () => {
    const client = startClient();
    try {
      for (const arguments_ of [
        { url: 'https://service.example' },
        { token: 'secret' },
        { registry: 'https://registry.example' },
        { package: 'other-mcp' },
        { serverPath: '/tmp/server.mjs' },
      ]) {
        const call = await client.request(1, 'tools/call', {
          name: 'spec_superflow_install_optional_mcp',
          arguments: arguments_,
        });
        assert.equal(call.result.isError, true);
        assert.match(call.result.content[0].text, /does not accept arguments/i);
        assert.doesNotMatch(call.result.content[0].text, /secret/);
      }
    } finally {
      client.close();
    }
  });

  it('keeps the workflow ready when optional MCP registration fails', async () => {
    const sandbox = makeRoot('ssf-optional-mcp-fail-');
    const pluginRoot = copyPluginRoot(sandbox);
    const userMcp = join(sandbox, 'user data', 'mcp.json');
    const code = join(sandbox, 'bin', 'code');
    fakeCode(code);
    const client = startClient({
      pluginRoot,
      env: {
        SPEC_SUPERFLOW_VSCODE_CLI: code,
        SPEC_SUPERFLOW_VSCODE_USER_MCP: userMcp,
        FAKE_CODE_MODE: 'fail',
      },
    });

    try {
      const result = parseTool(await client.request(1, 'tools/call', {
        name: 'spec_superflow_install_optional_mcp',
        arguments: {},
      }));
      assert.equal(result.status, 'blocked');
      assert.equal(result.configured, false);
      assert.equal(result.optional, true);
      assert.equal(result.workflowBlocking, false);
      assert.equal(result.reason, 'vscode-mcp-registration-failed');
      assert.equal(existsSync(userMcp), false);
    } finally {
      client.close();
    }
  });

  it('keeps status read-only and reports an exact installed CLI as ready', async () => {
    const sandbox = makeRoot('ssf-bootstrap-status-');
    const pluginRoot = copyPluginRoot(sandbox);
    const bin = join(sandbox, 'bin');
    const prefix = join(sandbox, 'prefix');
    fakeNpm(join(bin, 'npm'));
    fakeSsf(join(bin, 'ssf'), '0.14.0');
    const before = treeSnapshot(sandbox);
    const client = startClient({
      pluginRoot,
      env: {
        PATH: `${bin}:/usr/bin:/bin`,
        FAKE_NPM_PREFIX: prefix,
        FAKE_NPM_LOG: join(sandbox, 'npm.log'),
      },
    });

    try {
      const call = await client.request(1, 'tools/call', {
        name: 'spec_superflow_cli_status',
        arguments: {},
      });
      const status = parseTool(call);
      assert.equal(status.status, 'ready');
      assert.equal(status.pluginVersion, '0.14.0');
      assert.equal(status.cli.version, '0.14.0');
      assert.equal(status.installRequired, false);
      assert.equal(status.requiredAction, 'verify-with-ssf-version');
      assert.deepEqual(treeSnapshot(sandbox), before);
      assert.equal(existsSync(join(sandbox, 'npm.log')), false);
    } finally {
      client.close();
    }
  });

  it('installs a missing CLI through OpenCode from a Plugin path containing spaces and is idempotent', async () => {
    const sandbox = makeRoot('ssf-bootstrap-install-');
    const pluginRoot = copyPluginRoot(sandbox);
    const prefix = join(sandbox, 'global prefix');
    const bin = join(sandbox, 'tools');
    const log = join(sandbox, 'npm.log');
    fakeNpm(join(bin, 'npm'));
    mkdirSync(join(prefix, 'bin'), { recursive: true });
    const client = startClient({
      pluginRoot,
      env: {
        PATH: `${join(prefix, 'bin')}:${bin}:/usr/bin:/bin`,
        FAKE_NPM_PREFIX: prefix,
        FAKE_NPM_LOG: log,
        FAKE_INSTALL_VERSION: '0.14.0',
        SPEC_SUPERFLOW_PLUGIN_HOST: 'opencode',
      },
    });

    try {
      const first = parseTool(await client.request(1, 'tools/call', {
        name: 'spec_superflow_install_cli',
        arguments: {},
      }));
      assert.equal(first.status, 'ready');
      assert.equal(first.installed, true);
      assert.equal(first.cli.version, '0.14.0');

      const callsAfterFirst = readFileSync(log, 'utf8').trim().split('\n').map(JSON.parse);
      const install = callsAfterFirst.find(args => args[0] === 'install');
      assert.equal(install.at(-1), realpathSync(pluginRoot));
      assert.equal(install.filter(arg => arg === realpathSync(pluginRoot)).length, 1);
      assert.equal(install.includes('--install-links=true'), true);

      const second = parseTool(await client.request(2, 'tools/call', {
        name: 'spec_superflow_install_cli',
        arguments: {},
      }));
      assert.equal(second.status, 'ready');
      assert.equal(second.installed, false);
      const callsAfterSecond = readFileSync(log, 'utf8').trim().split('\n').map(JSON.parse);
      assert.equal(callsAfterSecond.filter(args => args[0] === 'install').length, 1);
    } finally {
      client.close();
    }
  });

  it('upgrades an older CLI through OpenCode and does not reinstall the exact version', async () => {
    const sandbox = makeRoot('ssf-opencode-bootstrap-upgrade-');
    const pluginRoot = copyPluginRoot(sandbox, 'OpenCode Plugin With Spaces');
    const prefix = join(sandbox, 'global prefix');
    const bin = join(prefix, 'bin');
    const tools = join(sandbox, 'tools');
    const log = join(sandbox, 'npm.log');
    fakeSsf(join(bin, 'ssf'), '0.13.0');
    fakeNpm(join(tools, 'npm'));
    const client = startClient({
      pluginRoot,
      env: {
        PATH: `${bin}:${tools}:/usr/bin:/bin`,
        FAKE_NPM_PREFIX: prefix,
        FAKE_NPM_LOG: log,
        FAKE_INSTALL_VERSION: '0.14.0',
        SPEC_SUPERFLOW_PLUGIN_HOST: 'opencode',
      },
    });

    try {
      const before = parseTool(await client.request(1, 'tools/call', {
        name: 'spec_superflow_cli_status',
        arguments: {},
      }));
      assert.equal(before.status, 'mismatch');
      assert.equal(before.cli.version, '0.13.0');
      assert.equal(before.requiredAction, 'request-install-confirmation');

      const upgraded = parseTool(await client.request(2, 'tools/call', {
        name: 'spec_superflow_install_cli',
        arguments: {},
      }));
      assert.equal(upgraded.status, 'ready');
      assert.equal(upgraded.cli.version, '0.14.0');
      assert.equal(upgraded.installed, true);
      assert.equal(upgraded.upgraded, true);

      const exact = parseTool(await client.request(3, 'tools/call', {
        name: 'spec_superflow_install_cli',
        arguments: {},
      }));
      assert.equal(exact.status, 'ready');
      assert.equal(exact.installed, false);
      assert.equal(exact.upgraded, false);

      const calls = readFileSync(log, 'utf8').trim().split('\n').map(JSON.parse);
      assert.equal(calls.filter(args => args[0] === 'install').length, 1);
      assert.equal(
        calls.find(args => args[0] === 'install').at(-1),
        realpathSync(pluginRoot),
      );
    } finally {
      client.close();
    }
  });

  it('tells the Agent to confirm installation when the CLI is missing', async () => {
    const sandbox = makeRoot('ssf-bootstrap-missing-action-');
    const pluginRoot = copyPluginRoot(sandbox);
    const bin = join(sandbox, 'tools');
    fakeNpm(join(bin, 'npm'));
    const client = startClient({
      pluginRoot,
      env: {
        PATH: `${bin}:/usr/bin:/bin`,
        FAKE_NPM_PREFIX: join(sandbox, 'prefix'),
      },
    });

    try {
      const status = parseTool(await client.request(1, 'tools/call', {
        name: 'spec_superflow_cli_status',
        arguments: {},
      }));
      assert.equal(status.status, 'missing');
      assert.equal(status.ready, false);
      assert.equal(status.requiredAction, 'request-install-confirmation');
    } finally {
      client.close();
    }
  });

  it('rejects arbitrary package, URL, registry, and path arguments', async () => {
    const client = startClient();
    try {
      for (const arguments_ of [
        { package: 'https://example.invalid/spec.tgz' },
        { registry: 'https://example.invalid' },
        { pluginRoot: '/tmp/other' },
      ]) {
        const call = await client.request(1, 'tools/call', {
          name: 'spec_superflow_install_cli',
          arguments: arguments_,
        });
        assert.equal(call.result.isError, true);
        assert.match(call.result.content[0].text, /does not accept arguments/i);
      }
    } finally {
      client.close();
    }
  });

  it('uses canonical Plugin paths and rejects a CLI resource symlink outside the Plugin', async () => {
    const sandbox = makeRoot('ssf-bootstrap-boundary-');
    const pluginRoot = copyPluginRoot(sandbox, 'real plugin');
    const linkedRoot = join(sandbox, 'linked plugin');
    symlinkSync(pluginRoot, linkedRoot, 'dir');
    const linkedClient = startClient({ pluginRoot: linkedRoot });
    try {
      const status = parseTool(await linkedClient.request(1, 'tools/call', {
        name: 'spec_superflow_cli_status',
        arguments: {},
      }));
      assert.equal(status.pluginRoot, realpathSync(pluginRoot));
    } finally {
      linkedClient.close();
    }

    const escapedRoot = copyPluginRoot(sandbox, 'escaped plugin');
    const outsideCli = join(sandbox, 'outside-cli.mjs');
    writeExecutable(outsideCli, `#!${process.execPath}\nconsole.log('0.14.0')\n`);
    rmSync(join(escapedRoot, 'scripts/spec-superflow.mjs'));
    symlinkSync(outsideCli, join(escapedRoot, 'scripts/spec-superflow.mjs'));
    const escapedClient = startClient({ pluginRoot: escapedRoot });
    try {
      const status = parseTool(await escapedClient.request(2, 'tools/call', {
        name: 'spec_superflow_cli_status',
        arguments: {},
      }));
      assert.equal(status.status, 'blocked');
      assert.equal(status.reason, 'invalid-plugin-package');
      assert.match(status.error, /outside PLUGIN_ROOT/);
    } finally {
      escapedClient.close();
    }
  });

  it('blocks when npm is missing without changing the CLI', async () => {
    const sandbox = makeRoot('ssf-bootstrap-no-npm-');
    const pluginRoot = copyPluginRoot(sandbox);
    const bin = join(sandbox, 'bin');
    fakeSsf(join(bin, 'ssf'), '0.13.0');
    fakeNode(join(bin, 'node'));
    const before = treeSnapshot(bin);
    const client = startClient({
      pluginRoot,
      env: {
        PATH: `${bin}:/usr/bin:/bin`,
        SPEC_SUPERFLOW_PLUGIN_HOST: 'opencode',
      },
    });
    try {
      const status = parseTool(await client.request(1, 'tools/call', {
        name: 'spec_superflow_cli_status',
        arguments: {},
      }));
      assert.equal(status.status, 'blocked');
      assert.equal(status.reason, 'npm-missing');
      assert.match(status.recovery, /restart OpenCode/);
      assert.doesNotMatch(status.recovery, /VS Code/);

      const result = parseTool(await client.request(2, 'tools/call', {
        name: 'spec_superflow_install_cli',
        arguments: {},
      }));
      assert.equal(result.status, 'blocked');
      assert.equal(result.reason, 'npm-missing');
      assert.match(result.recovery, /restart OpenCode/);
      assert.deepEqual(treeSnapshot(bin), before);
    } finally {
      client.close();
    }
  });

  it('blocks when an external Node.js runtime is missing from PATH', async () => {
    const sandbox = makeRoot('ssf-bootstrap-no-node-');
    const pluginRoot = copyPluginRoot(sandbox);
    const emptyBin = join(sandbox, 'empty-bin');
    mkdirSync(emptyBin, { recursive: true });
    const client = startClient({
      pluginRoot,
      env: {
        PATH: emptyBin,
        SPEC_SUPERFLOW_PLUGIN_HOST: 'opencode',
      },
    });
    try {
      const result = parseTool(await client.request(1, 'tools/call', {
        name: 'spec_superflow_cli_status',
        arguments: {},
      }));
      assert.equal(result.status, 'blocked');
      assert.equal(result.ready, false);
      assert.equal(result.installRequired, false);
      assert.equal(result.reason, 'node-missing');
      assert.deepEqual(result.node, {
        available: false,
        path: null,
        version: null,
      });
      assert.equal(result.npm.available, false);
      assert.equal(result.cli.available, false);
      assert.match(result.recovery, /restart OpenCode/);
      assert.doesNotMatch(result.recovery, /VS Code/);
    } finally {
      client.close();
    }
  });

  it('rolls back an existing CLI when npm upgrade fails destructively', async () => {
    const sandbox = makeRoot('ssf-bootstrap-rollback-');
    const pluginRoot = copyPluginRoot(sandbox);
    const prefix = join(sandbox, 'prefix');
    const bin = join(prefix, 'bin');
    const npmBin = join(sandbox, 'tools');
    const oldCli = join(bin, 'ssf');
    fakeSsf(oldCli, '0.13.0');
    fakeNpm(join(npmBin, 'npm'));
    const before = readFileSync(oldCli);
    const client = startClient({
      pluginRoot,
      env: {
        PATH: `${bin}:${npmBin}:/usr/bin:/bin`,
        FAKE_NPM_PREFIX: prefix,
        FAKE_NPM_MODE: 'fail',
        FAKE_NPM_DELETE_EXISTING: '1',
      },
    });

    try {
      const result = parseTool(await client.request(1, 'tools/call', {
        name: 'spec_superflow_install_cli',
        arguments: {},
      }));
      assert.equal(result.status, 'blocked');
      assert.equal(result.rolledBack, true);
      assert.equal(result.previousCli.version, '0.13.0');
      assert.deepEqual(readFileSync(oldCli), before);
      const execution = await import('node:child_process').then(({ spawnSync }) =>
        spawnSync(oldCli, ['--version'], { encoding: 'utf8' }));
      assert.equal(execution.status, 0);
      assert.equal(execution.stdout.trim(), '0.13.0');
      assert.match(result.recovery, /previous CLI.*restored/i);
    } finally {
      client.close();
    }
  });

  it('rolls back when npm succeeds but installs the wrong version', async () => {
    const sandbox = makeRoot('ssf-bootstrap-drift-');
    const pluginRoot = copyPluginRoot(sandbox);
    const prefix = join(sandbox, 'prefix');
    const bin = join(prefix, 'bin');
    const npmBin = join(sandbox, 'tools');
    const oldCli = join(bin, 'ssf');
    fakeSsf(oldCli, '0.13.0');
    fakeNpm(join(npmBin, 'npm'));
    const client = startClient({
      pluginRoot,
      env: {
        PATH: `${bin}:${npmBin}:/usr/bin:/bin`,
        FAKE_NPM_PREFIX: prefix,
        FAKE_INSTALL_VERSION: '9.9.9',
      },
    });

    try {
      const result = parseTool(await client.request(1, 'tools/call', {
        name: 'spec_superflow_install_cli',
        arguments: {},
      }));
      assert.equal(result.status, 'blocked');
      assert.equal(result.reason, 'version-mismatch-after-install');
      assert.equal(result.rolledBack, true);
      assert.equal(result.previousCli.version, '0.13.0');
      const status = parseTool(await client.request(2, 'tools/call', {
        name: 'spec_superflow_cli_status',
        arguments: {},
      }));
      assert.equal(status.cli.version, '0.13.0');
    } finally {
      client.close();
    }
  });

  it('does not report ready when npm bin is outside PATH', async () => {
    const sandbox = makeRoot('ssf-bootstrap-hidden-bin-');
    const pluginRoot = copyPluginRoot(sandbox);
    const prefix = join(sandbox, 'prefix');
    const npmBin = join(sandbox, 'tools');
    fakeNpm(join(npmBin, 'npm'));
    const client = startClient({
      pluginRoot,
      env: {
        PATH: `${npmBin}:/usr/bin:/bin`,
        FAKE_NPM_PREFIX: prefix,
        FAKE_INSTALL_VERSION: '0.14.0',
        SPEC_SUPERFLOW_PLUGIN_HOST: 'opencode',
      },
    });

    try {
      const result = parseTool(await client.request(1, 'tools/call', {
        name: 'spec_superflow_install_cli',
        arguments: {},
      }));
      assert.equal(result.status, 'blocked');
      assert.equal(result.reason, 'installed-cli-not-on-path');
      assert.match(result.recovery, /PATH/);
      assert.match(result.recovery, /restart OpenCode/);
      assert.doesNotMatch(result.recovery, /VS Code/);
      assert.equal(statSync(join(prefix, 'bin', 'ssf')).isFile(), true);
    } finally {
      client.close();
    }
  });

  it('preserves VS Code recovery wording for Node npm and installed CLI PATH', async () => {
    const nodeSandbox = makeRoot('ssf-vscode-recovery-node-');
    const nodePlugin = copyPluginRoot(nodeSandbox);
    const emptyBin = join(nodeSandbox, 'empty-bin');
    mkdirSync(emptyBin, { recursive: true });
    const nodeClient = startClient({ pluginRoot: nodePlugin, env: { PATH: emptyBin } });
    try {
      const status = parseTool(await nodeClient.request(1, 'tools/call', {
        name: 'spec_superflow_cli_status',
        arguments: {},
      }));
      assert.equal(
        status.recovery,
        'Install Node.js, add it to PATH, restart VS Code, and run workflow-init again.',
      );
    } finally {
      nodeClient.close();
    }

    const npmSandbox = makeRoot('ssf-vscode-recovery-npm-');
    const npmPlugin = copyPluginRoot(npmSandbox);
    const npmBinOnly = join(npmSandbox, 'bin');
    fakeNode(join(npmBinOnly, 'node'));
    const npmClient = startClient({
      pluginRoot: npmPlugin,
      env: { PATH: `${npmBinOnly}:/usr/bin:/bin` },
    });
    try {
      const result = parseTool(await npmClient.request(1, 'tools/call', {
        name: 'spec_superflow_install_cli',
        arguments: {},
      }));
      assert.equal(
        result.recovery,
        'Install Node.js with npm, then run workflow-init again.',
      );
    } finally {
      npmClient.close();
    }

    const pathSandbox = makeRoot('ssf-vscode-recovery-path-');
    const pathPlugin = copyPluginRoot(pathSandbox);
    const prefix = join(pathSandbox, 'prefix');
    const tools = join(pathSandbox, 'tools');
    fakeNpm(join(tools, 'npm'));
    const pathClient = startClient({
      pluginRoot: pathPlugin,
      env: {
        PATH: `${tools}:/usr/bin:/bin`,
        FAKE_NPM_PREFIX: prefix,
        FAKE_INSTALL_VERSION: '0.14.0',
      },
    });
    try {
      const result = parseTool(await pathClient.request(1, 'tools/call', {
        name: 'spec_superflow_install_cli',
        arguments: {},
      }));
      assert.equal(
        result.recovery,
        `Add ${join(prefix, 'bin')} to PATH, restart VS Code, and run workflow-init again.`,
      );
    } finally {
      pathClient.close();
    }
  });
});
