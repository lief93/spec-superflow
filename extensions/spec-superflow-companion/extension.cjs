'use strict';

const TOOL_NAME = 'spec_superflow_companion_probe';

function probePayload() {
  return {
    ok: true,
    source: 'spec-superflow-companion-vsix',
    networkUsed: false,
  };
}

function activate(context) {
  const vscode = require('vscode');
  const registration = vscode.lm.registerTool(TOOL_NAME, {
    invoke() {
      return new vscode.LanguageModelToolResult([
        new vscode.LanguageModelTextPart(JSON.stringify(probePayload())),
      ]);
    },
  });
  context.subscriptions.push(registration);
}

module.exports = { activate, probePayload };
