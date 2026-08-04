# Use Spec Superflow in VS Code

The offline VSIX contains the Spec Agent Plugin, `/workflow-init` tools, CLI
source, and a replaceable Example MCP bridge. A VS Code user installs one file;
do not also install the same Agent Plugin from Git, because that can create
duplicate Spec Agents.

## 1. Install the Offline VSIX

Prerequisites: Node.js and npm are installed, and GitHub Copilot is signed in
and enabled in VS Code.

1. Copy `spec-superflow-<version>.vsix` to the offline computer.
2. Open the Command Palette.
3. Select **Extensions: Install from VSIX...** and choose that file.
4. Reload VS Code when prompted.
5. Confirm that **Spec Superflow** appears once in the Chat Agent selector.

## 2. Run `/workflow-init`

1. Keep the built-in VS Code **Agent** selected.
2. Enter `/workflow-init` and select the structured Slash Command suggestion.
3. If the global `ssf` CLI is missing or has another version, approve the
   offline installation or upgrade.
4. Wait for `READY`, then select **Return to Agent**.

`/workflow-init` only checks, installs, upgrades, and verifies the global CLI.
It does not inspect the project, create a Change, start a requirement, or
configure a business MCP. The command can be run repeatedly in the same Chat.

## 3. Try the Replaceable Example MCP

The VSIX includes an `example-mcp-reader` Skill. For example, ask:

```text
Use the Example MCP to read MOBILE-123.
```

The Skill calls `spec_superflow_example_mcp_read` with only the item URL or
key. On the first call, VS Code visibly prompts for an example service URL and
Token. The URL is kept in extension state and the Token in VS Code
SecretStorage; neither is sent through Chat or returned by the tool.

The VSIX starts its bundled stdio Example MCP, performs one fixed call, and
closes the process. The upstream example returns deterministic local data and
does not access the network. In a company fork, replace the bundled example
Server and fixed tool mapping with the company Jira MCP while retaining the
same Skill and one-shot lifecycle.

## 4. Initialize a Business Project

1. Open the repository root.
2. Select **Spec Superflow**.
3. Enter `Initialize the current project`.
4. Review the generated project baseline and add constraints that cannot be
   inferred from the code.

`project-init` does not check, install, or upgrade the CLI.

## 5. Start or Continue a Requirement

1. Select **Spec Superflow**.
2. Describe the requirement, bug, or existing Change to resume.
3. Confirm scope and planning decisions when requested.
4. The fixed independent Reviewer runs at the configured planning and final
   checkpoints.
5. Implementation begins only after Planning and its execution contract are
   approved.

## 6. Update

1. Copy the new offline VSIX to the computer.
2. Run **Extensions: Install from VSIX...** again and select it.
3. Reload VS Code.
4. Run `/workflow-init`; approve the global CLI upgrade when requested.

## 7. Troubleshooting

### `/workflow-init` or its tools are unavailable

- Confirm the VSIX is installed and enabled.
- Confirm only one copy of Spec Superflow is installed.
- Keep the built-in **Agent** selected when entering `/workflow-init`.
- Select the Slash Command suggestion instead of sending plain text.
- Run **Developer: Reload Window** and retry.
- In Chat **Configure Tools**, confirm `specSuperflowCliStatus` and
  `specSuperflowInstallCli` are available.

The combined VSIX uses VS Code Language Model Tools and does not require the
native VS Code MCP Host. An empty **MCP: List Servers** view does not prevent
these tools from working.

### CLI installation or upgrade fails

- Confirm `node --version` and `npm --version` work.
- Run `npm prefix -g` to identify the global installation prefix.
- Resolve the permission or PATH error returned by `/workflow-init`.
- Run `/workflow-init` again. It reports `READY` only when the global CLI and
  bundled Plugin versions match exactly.

### The Example MCP does not run

- In Chat **Configure Tools**, confirm `specSuperflowExampleMcpRead` is
  available.
- Retry and complete both visible credential prompts.
- Do not paste a Token into Chat or pass it as an item argument.
- Remember that the upstream Server is an offline integration example; a
  company fork must replace its deterministic response with the company MCP.
