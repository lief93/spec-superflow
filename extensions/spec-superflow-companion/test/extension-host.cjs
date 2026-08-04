'use strict';

const assert = require('node:assert/strict');
const vscode = require('vscode');

const EXTENSION_ID = 'magebyte.spec-superflow-companion';
const TOOLS = [
  'spec_superflow_cli_status',
  'spec_superflow_install_cli',
  'spec_superflow_example_mcp_read',
];

async function run() {
  const extension = vscode.extensions.getExtension(EXTENSION_ID);
  assert.ok(extension, `${EXTENSION_ID} was not discovered`);
  await extension.activate();

  for (const name of TOOLS) {
    assert.ok(vscode.lm.tools.some(tool => tool.name === name), `${name} was not registered`);
  }
  const result = await vscode.lm.invokeTool('spec_superflow_cli_status', { input: {} });
  const text = result.content.find(part => part instanceof vscode.LanguageModelTextPart);
  const value = JSON.parse(text?.value ?? '{}');
  assert.equal(value.pluginVersion, '0.15.0');
  assert.match(value.pluginRoot, /agent-plugin$/);
}

module.exports = { run };
