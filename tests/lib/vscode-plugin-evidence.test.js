import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';

const ROOT = process.cwd();
const read = path => readFileSync(join(ROOT, path), 'utf8');

describe('VS Code Plugin documentation boundary', () => {
  it('keeps bootstrap implementation details in code and user setup steps in docs', () => {
    const productionMcp = JSON.parse(read('.mcp.json'));
    const server = read('servers/spec-superflow-mcp.mjs');
    const reference = read('docs/vscode-agent-plugin.md');
    const guide = read('docs/vscode-agent-plugin-zh.md');

    assert.ok(productionMcp.mcpServers['spec-superflow']);
    for (const tool of [
      'spec_superflow_cli_status',
      'spec_superflow_install_cli',
      'spec_superflow_optional_mcp_status',
      'spec_superflow_install_optional_mcp',
    ]) {
      assert.match(server, new RegExp(tool));
    }
    assert.doesNotMatch(server, /spec_superflow_run/);
    assert.match(reference, /business MCP is optional/i);
    assert.match(reference, /workflow.*READY.*optionalMcp.*SKIPPED/is);
    assert.match(reference, /keeps both values visible/i);
    assert.match(reference, /VS Code[\s\S]*secure credentials\s+store/i);
    assert.match(reference, /spec-superflow-mcp-launcher\.cmd/);
    assert.match(guide, /Choose whether to configure the optional MCP/i);
    assert.match(guide, /MCP: List Servers/i);
    assert.match(guide, /URL, Token, or other values/i);
  });

  it('documents workflow-init as the only install entry and local Plugin source ownership', () => {
    const reference = read('docs/vscode-agent-plugin.md');
    const guide = read('docs/vscode-agent-plugin-zh.md');

    assert.match(reference, /type `\/workflow-init`/i);
    assert.match(
      reference,
      /setup reports `workflow=READY`[\s\S]*select \*\*Spec Superflow\*\* and describe a\s+requirement/i,
    );
    assert.match(
      reference,
      /built-in \*\*Agent\*\*[\s\S]*type `\/workflow-init`[\s\S]*Click it or press \*\*Tab\*\*/i,
    );
    assert.match(
      guide,
      /built-in VS Code \*\*Agent\*\*[\s\S]*Enter `\/workflow-init`[\s\S]*press\s+\*\*Tab\*\*/i,
    );
    assert.match(guide, /workflow=READY[\s\S]*Select \*\*Spec Superflow\*\*/i);
    assert.match(reference, /Run `\/workflow-init` before starting a requirement/i);
    assert.match(guide, /only installs, verifies, or updates the workflow runtime/i);
    assert.doesNotMatch(`${reference}\n${guide}`, /continues the original request once/i);
    assert.match(reference, /current `\$\{PLUGIN_ROOT\}` only/);
    assert.match(reference, /no second Spec repository or archive is required/i);
    assert.doesNotMatch(guide, /公司|内网/);
  });

  it('keeps direct CLI and project instruction ownership in their authoritative files', () => {
    const workflow = read('skills/workflow-start/SKILL.md');
    const projectInit = read('skills/project-init/SKILL.md');
    const reference = read('docs/vscode-agent-plugin.md');
    const guide = read('docs/vscode-agent-plugin-zh.md');

    assert.match(workflow, /ssf state init/);
    assert.match(workflow, /ssf state transition/);
    assert.match(projectInit, /\.github\/instructions\/spec-superflow\.instructions\.md/);
    assert.match(projectInit, /Leave an existing `\.github\/copilot-instructions\.md` byte-for-byte unchanged/);
    assert.match(reference, /Skills execute `ssf state`/);
    assert.match(reference, /\.github\/instructions\/spec-superflow\.instructions\.md/);
    assert.match(guide, /Initialize the current project/i);
    assert.match(guide, /Review the generated project rules and development baseline/i);
  });
});
