# Use Spec Superflow in VS Code

Install the Spec Superflow Plugin once to use the same Agents, Skills,
Commands, and MCP servers across multiple projects. Business repositories do
not need copies of the shared workflow files.

## 1. Install the Plugin

Prerequisites: Node.js and npm are installed, and GitHub Copilot is signed in
and enabled in VS Code.

1. Open VS Code.
2. Press `Cmd + Shift + P` on macOS or `Ctrl + Shift + P` on Windows/Linux to
   open the Command Palette.
3. Enter and select **Chat: Install Plugin From Source**.
4. Follow the prompt to enter the Spec Superflow Plugin repository Git URL or
   select a local Plugin directory.
5. Wait for installation to finish. Select **Reload** if VS Code asks to reload
   the window.
6. Open Agent Plugins and confirm that **Spec Superflow** is enabled and
   available in the Chat Agent selector.

The Plugin only needs to be installed once to serve multiple business
projects.

## 2. Run `/workflow-init`

1. Open a new Chat.
2. Keep the built-in VS Code **Agent** selected. Do not select
   **Spec Superflow** yet.
3. Enter `/workflow-init`.
4. Click the Plugin-provided command in the suggestion list, or press **Tab**
   to select it, then send it. Do not send the suggestion text as a regular
   Chat message.
5. If the global `ssf` CLI is missing or its version differs from the Plugin,
   confirm the installation or upgrade when prompted.
6. Wait for initialization to finish.

The workflow is available when the result contains:

```text
workflow=READY
```

`/workflow-init` only installs, upgrades, and verifies the workflow runtime.
It does not inspect the current business project, create a Change, or start a
requirement.

## 3. Configure an Optional MCP

If `/workflow-init` asks whether to configure an optional MCP:

- Skipping it does not block the Spec workflow. The result is
  `workflow=READY, optionalMcp=SKIPPED`.
- If you choose to configure it, wait for
  `workflow=READY, optionalMcp=REGISTERED`, then continue with the steps below.

Configuration steps:

1. Open the VS Code Command Palette.
2. Enter and select **MCP: List Servers**.
3. Select **spec-superflow-optional-example**.
4. Select **Start Server**.
5. Enter the service URL and Token in the native VS Code prompts. Do not send
   credentials through Chat.
6. Run `/workflow-init` again.

The optional MCP is callable when the result contains:

```text
workflow=READY, optionalMcp=READY
```

If the result contains `optionalMcp=BLOCKED`, the Spec workflow remains
available; only that optional MCP is unavailable.

## 4. Initialize a Business Project

When using the workflow in a business repository for the first time:

1. Open the repository root in VS Code.
2. Select **Spec Superflow** from the Chat Agent selector.
3. Enter `Initialize the current project`.
4. Review the generated project rules and development baseline. Add runtime
   configuration, team constraints, or architecture requirements that cannot
   be inferred from the code.

Skip this step if the project has already been initialized. `project-init`
does not install or upgrade the CLI.

## 5. Start or Continue a Requirement

1. Select **Spec Superflow** in Chat.
2. Describe the requirement or bug, or identify an existing Change to resume.
3. Confirm the scope, planning results, and execution approach when prompted.
4. The independent Reviewer runs automatically at the fixed planning and final
   implementation checkpoints. If it finds an issue, the workflow repairs the
   candidate and reviews it again.
5. The Agent changes business code and tests only after planning and the
   execution contract are approved.
6. Follow the prompts to complete testing, final review, and closing.

Selecting another Agent stops applying the Spec Superflow workflow
instructions. You do not need to uninstall the Plugin.

## 6. Update the Plugin

1. Update Spec Superflow from Agent Plugins. If the installed VS Code version
   does not provide an update action, run
   **Chat: Install Plugin From Source** again with the same repository URL.
2. Reload VS Code.
3. Open a new Chat and keep the built-in VS Code **Agent** selected.
4. Run `/workflow-init` again.
5. If the Plugin version is newer than the installed CLI, confirm the upgrade.
6. After the result contains `workflow=READY`, select **Spec Superflow** and
   continue the requirement.

Updating the Plugin does not require copying shared Agents, Skills, or scripts
into each business project.

## 7. Troubleshooting

### `/workflow-init` Is Not Available

- Confirm that the Plugin is installed and enabled.
- Open a new Chat and enter `/workflow-init` again.
- Click the suggestion or press **Tab** to select it instead of sending the
  suggestion text as a regular message.
- Run **Developer: Reload Window** and retry.

### Installation Cannot Find the Plugin or Git Clone Fails

- Confirm that the repository URL can be cloned from the current computer.
- Confirm that `plugin.json` is at the repository root, not in a parent or
  nested directory.
- Confirm that the current account can access the internal Git repository.
- When using a local path, confirm that it points to the complete Plugin root.

### Initialization Cannot Find `spec_superflow_cli_status`

- Confirm that the Plugin is enabled.
- Open **MCP: List Servers** and confirm that the `spec-superflow` bootstrap MCP
  is present.
- Confirm that the workspace is not in **Restricted Mode**.
- Run **Developer: Reload Window**, open a new Chat, and retry.

### `MCP: List Servers` Is Empty

- Confirm that the Agent Plugin is enabled.
- Run **Workspaces: Manage Workspace Trust** and confirm that the workspace is
  **Trusted**.
- Check whether an organization policy has disabled MCP access.
- Inspect the **GitHub Copilot Chat**, **MCP**, and **Extension Host** channels
  in Output.

### CLI Installation or Upgrade Fails

- Confirm that the terminal can run `node --version` and `npm --version`.
- Resolve the permission or PATH issue reported by `/workflow-init`.
- Run `/workflow-init` again after resolving the issue.
- The workflow reports `workflow=READY` only when the CLI and Plugin versions
  match exactly.
