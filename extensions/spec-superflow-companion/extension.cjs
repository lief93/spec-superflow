'use strict';

const { spawn } = require('node:child_process');
const { createInterface } = require('node:readline');
const { join } = require('node:path');

const CLI_STATUS = 'spec_superflow_cli_status';
const CLI_INSTALL = 'spec_superflow_install_cli';
const EXAMPLE_READ = 'spec_superflow_example_mcp_read';
const EXAMPLE_SERVER_TOOL = 'spec_superflow_example_read_item';
const EXAMPLE_URL_KEY = 'specSuperflow.exampleMcp.url';
const EXAMPLE_TOKEN_KEY = 'specSuperflow.exampleMcp.token';

function languageModelResult(vscode, value) {
  return new vscode.LanguageModelToolResult([
    new vscode.LanguageModelTextPart(JSON.stringify(value)),
  ]);
}

function serverResult(result) {
  const text = result?.content?.find(item => item.type === 'text')?.text;
  if (!text) throw new Error('The MCP tool returned no text result.');
  return JSON.parse(text);
}

async function callOneShotMcp({ launcher, server, tool, arguments_ = {}, env = process.env }) {
  const windows = process.platform === 'win32';
  const command = windows ? launcher : '/bin/sh';
  const args = windows ? [server] : [launcher, server];
  const child = spawn(command, args, {
    env: { ...env, SPEC_SUPERFLOW_PLUGIN_HOST: 'vscode-extension' },
    shell: windows,
    stdio: ['pipe', 'pipe', 'pipe'],
    windowsHide: true,
  });
  const lines = createInterface({ input: child.stdout })[Symbol.asyncIterator]();
  const timeout = setTimeout(() => child.kill(), 15_000);
  let nextId = 0;
  let stderr = '';
  child.stderr.setEncoding('utf8');
  child.stderr.on('data', chunk => {
    stderr += chunk;
  });

  async function request(method, params = {}) {
    const id = ++nextId;
    child.stdin.write(`${JSON.stringify({ jsonrpc: '2.0', id, method, params })}\n`);
    const { value: line, done } = await lines.next();
    if (done) throw new Error(`${method} received no response${stderr ? `: ${stderr.trim()}` : ''}`);
    const message = JSON.parse(line);
    if (message.id !== id) throw new Error(`${method} returned an unexpected response id.`);
    if (message.error) throw new Error(message.error.message);
    return message.result;
  }

  try {
    await request('initialize', {
      protocolVersion: '2025-06-18',
      capabilities: {},
      clientInfo: { name: 'spec-superflow-vscode', version: '0.15.0' },
    });
    child.stdin.write(`${JSON.stringify({
      jsonrpc: '2.0',
      method: 'notifications/initialized',
      params: {},
    })}\n`);
    const listed = await request('tools/list');
    if (!listed.tools?.some(candidate => candidate.name === tool)) {
      throw new Error(`Bundled MCP did not expose the fixed tool ${tool}.`);
    }
    const called = await request('tools/call', { name: tool, arguments: arguments_ });
    child.stdin.end();
    await new Promise((resolve, reject) => {
      child.once('close', code => code === 0
        ? resolve()
        : reject(new Error(`Bundled MCP exited with code ${code}${stderr ? `: ${stderr.trim()}` : ''}`)));
    });
    return serverResult(called);
  } finally {
    clearTimeout(timeout);
    if (child.exitCode === null && child.signalCode === null) child.kill();
  }
}

async function exampleCredentials(vscode, context) {
  let url = context.globalState.get(EXAMPLE_URL_KEY);
  let token = await context.secrets.get(EXAMPLE_TOKEN_KEY);
  if (!url) {
    url = await vscode.window.showInputBox({
      title: 'Configure Example MCP',
      prompt: 'Service URL (replace this prompt when adapting the example to Jira)',
      placeHolder: 'https://service.example/mcp',
      ignoreFocusOut: true,
    });
    if (!url) return null;
  }
  if (!token) {
    token = await vscode.window.showInputBox({
      title: 'Configure Example MCP',
      prompt: 'Token (stored in VS Code SecretStorage and never passed through Chat)',
      password: true,
      ignoreFocusOut: true,
    });
    if (!token) return null;
  }
  await context.globalState.update(EXAMPLE_URL_KEY, url);
  await context.secrets.store(EXAMPLE_TOKEN_KEY, token);
  return { url, token };
}

function activate(context) {
  const vscode = require('vscode');
  const pluginRoot = join(context.extensionPath, 'agent-plugin');
  const launcher = join(pluginRoot, 'servers', 'spec-superflow-mcp-launcher.cmd');
  const bootstrapServer = join(pluginRoot, 'servers', 'spec-superflow-mcp.mjs');
  const exampleServer = join(pluginRoot, 'servers', 'example-item-mcp.mjs');

  const registrations = [
    vscode.lm.registerTool(CLI_STATUS, {
      async invoke() {
        const value = await callOneShotMcp({
          launcher,
          server: bootstrapServer,
          tool: CLI_STATUS,
        });
        return languageModelResult(vscode, value);
      },
    }),
    vscode.lm.registerTool(CLI_INSTALL, {
      async invoke() {
        const value = await callOneShotMcp({
          launcher,
          server: bootstrapServer,
          tool: CLI_INSTALL,
        });
        return languageModelResult(vscode, value);
      },
    }),
    vscode.lm.registerTool(EXAMPLE_READ, {
      async invoke(options) {
        const credentials = await exampleCredentials(vscode, context);
        if (!credentials) {
          return languageModelResult(vscode, {
            status: 'cancelled',
            reason: 'example-mcp-credential-entry-cancelled',
          });
        }
        const value = await callOneShotMcp({
          launcher,
          server: exampleServer,
          tool: EXAMPLE_SERVER_TOOL,
          arguments_: { item: options.input.item },
          env: {
            ...process.env,
            SPEC_SUPERFLOW_EXAMPLE_URL: credentials.url,
            SPEC_SUPERFLOW_EXAMPLE_TOKEN: credentials.token,
          },
        });
        return languageModelResult(vscode, value);
      },
    }),
  ];
  context.subscriptions.push(...registrations);
}

module.exports = {
  activate,
  callOneShotMcp,
  serverResult,
};
