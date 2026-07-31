# Use Spec Superflow in VS Code

Install the Spec Superflow Plugin once to use the same Agents, Skills,
Commands, and MCP servers across multiple projects. Business repositories do
not need copies of the workflow files.

## 1. Install the Plugin

1. Open VS Code.
2. Press `Cmd + Shift + P` on macOS or `Ctrl + Shift + P` on Windows/Linux to
   open the Command Palette.
3. Enter and select **Chat: Install Plugin From Source**.
4. Follow the prompt to enter the Plugin repository Git URL or select a local
   Plugin folder.
5. Wait for installation to finish. Select **Reload** if VS Code asks to reload
   the window.

After installation, confirm that **Spec Superflow** is enabled in the Agent
Plugins list and appears in the Chat Agent selector.

## 2. Initialize or Update the Workflow

1. Open a new Chat.
2. Keep the built-in VS Code **Agent** selected. Do not select
   **Spec Superflow** yet.
3. Enter `/workflow-init`.
4. Click the command provided by the Plugin in the suggestion list, or press
   **Tab** to select it. The suggestion may appear as
   `/spec-superflow workflow-init` or `/<team-plugin-name> workflow-init`.
5. Send the command.
6. Confirm installation or upgrade if prompted for the `ssf` CLI.
7. Choose whether to configure the optional MCP. Skipping it does not block the
   Spec workflow.

The workflow is ready when the result contains:

```text
workflow=READY
```

`/workflow-init` only installs, verifies, or updates the workflow runtime. It
does not create a requirement, inspect the project, or generate a Change.

## 3. Configure an Optional MCP

Only follow these steps after choosing to configure an MCP during
`/workflow-init`:

1. Press `Cmd/Ctrl + Shift + P` to open the Command Palette.
2. Enter and select **MCP: List Servers**.
3. Select the required Server, then select **Start Server**.
4. Enter the URL, Token, or other values if VS Code prompts for them.
5. Run `/workflow-init` again to verify the configuration.

The MCP is ready when the result contains:

```text
workflow=READY, optionalMcp=READY
```

If the result contains `optionalMcp=SKIPPED` or `optionalMcp=BLOCKED`, the Spec
workflow remains available; only that optional MCP is unavailable.

## 4. Initialize a Project

When using the workflow in a business repository for the first time:

1. Open the repository root in VS Code.
2. Select **Spec Superflow** from the Chat Agent selector.
3. Enter `Initialize the current project`.
4. Review the generated project rules and development baseline. Add runtime
   configuration or team constraints that cannot be inferred from the code.

Skip this step if the project has already been initialized.

## 5. Start or Continue a Requirement

1. Select **Spec Superflow** in Chat.
2. Describe the requirement, bug, or existing Change to continue.
3. Review and approve the requirement, Spec, Design, Tasks, and execution
   contract when prompted.
4. The Agent starts changing code and tests only after the execution contract
   is approved.
5. Follow the prompts to complete testing, review, and closure.

Selecting another Agent stops applying the Spec Superflow Agent instructions.
You do not need to uninstall the Plugin.

## 6. Update the Plugin

1. Update the Plugin from Agent Plugins. If the installed VS Code version does
   not provide an update action, use **Chat: Install Plugin From Source** to
   install the same source again.
2. Reload VS Code.
3. Run `/workflow-init` again in a new Chat.
4. Confirm the upgrade if the Plugin version is newer than the installed CLI.
5. Continue after the result contains `workflow=READY`.

## 7. Troubleshooting

### `/workflow-init` Is Not Available

- Confirm that the Plugin is installed and enabled.
- Open a new Chat and enter `/workflow-init` again.
- Click the suggestion or press **Tab** to select it instead of sending the
  suggestion text as a regular message.
- Run **Developer: Reload Window** and retry.

### Initialization Cannot Find `spec_superflow_cli_status`

The Plugin bootstrap MCP is not available in the current Chat:

- Confirm that the Plugin is enabled.
- Run **MCP: List Servers** and check for `spec-superflow`.
- Confirm that the workspace is not in **Restricted Mode**.
- Run **Developer: Reload Window**, open a new Chat, and retry.

### `MCP: List Servers` Is Empty

- Confirm that the Agent Plugin is enabled.
- Run **Workspaces: Manage Workspace Trust** and confirm that the workspace is
  **Trusted**.
- Search Settings for `chat.mcp.access` and confirm that MCP access is not
  disabled by an organization policy.
- Set the log level to **Trace**, then inspect the **GitHub Copilot Chat**,
  **MCP**, and **Extension Host** channels in Output.

### CLI Installation Fails

- Confirm that the terminal can run `node --version` and `npm --version`.
- Resolve the permission or PATH issue reported by `/workflow-init`, then
  retry.
- The command reports `workflow=READY` only after the version check succeeds.
