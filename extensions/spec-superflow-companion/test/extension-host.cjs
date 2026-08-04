'use strict';

const assert = require('node:assert/strict');
const vscode = require('vscode');

const EXTENSION_ID = 'magebyte.spec-superflow-companion';
const TOOL_NAME = 'spec_superflow_companion_probe';

async function run() {
  const extension = vscode.extensions.getExtension(EXTENSION_ID);
  assert.ok(extension, `${EXTENSION_ID} was not discovered`);
  await extension.activate();

  assert.ok(vscode.lm.tools.some(tool => tool.name === TOOL_NAME), `${TOOL_NAME} was not registered`);
  const result = await vscode.lm.invokeTool(TOOL_NAME, { input: {} });
  const text = result.content.find(part => part instanceof vscode.LanguageModelTextPart);
  assert.equal(
    text?.value,
    JSON.stringify({
      ok: true,
      source: 'spec-superflow-companion-vsix',
      networkUsed: false,
    }),
  );
}

module.exports = { run };
