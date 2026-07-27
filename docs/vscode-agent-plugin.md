# VS Code Spec Superflow Agent Plugin

The complete Spec Superflow repository is installed as one Agent Plugin. It
contains the Agent, Skills, Commands, templates, CLI source, and a small
bootstrap MCP server. Target repositories do not need a copy of those central
resources or a separate Spec Superflow download.

## Repository layout

```text
spec-superflow-plugin/
  .plugin/plugin.json
  plugin.json
  agents/
  skills/
  commands/
  servers/spec-superflow-mcp-launcher.cmd
  servers/spec-superflow-mcp.mjs
  scripts/
  templates/
  .mcp.json
  package.json
  .github/plugin/marketplace.json   # optional distribution metadata
```

VS Code checks `.plugin/plugin.json`, root `plugin.json`,
`.github/plugin/plugin.json`, and `.claude-plugin/plugin.json`, in that order.
This repository uses the OpenPlugin manifest so `.mcp.json` can start a bundled
server through `${PLUGIN_ROOT}`.

The manifest uses a kebab-case `name`, semantic `version`, `author` object, and
valid relative component paths. Skills live at
`skills/<name>/SKILL.md`, Agents use `*.agent.md`, and Commands are Markdown
prompt files under `commands/`. The `/workflow-init` prompt declares its
`name`, target `agent`, and restricted `tools`; `allowed-tools` is not a VS Code
prompt-file field.

## Runtime model

The bootstrap MCP server exposes four setup tools:

- `spec_superflow_cli_status`: a read-only check of Node, npm, the installed
  `ssf` path/version, and the Plugin version.
- `spec_superflow_install_cli`: after user confirmation, installs or updates
  the global CLI from the current `${PLUGIN_ROOT}` only.
- `spec_superflow_optional_mcp_status`: checks whether the bundled optional MCP
  definition is registered without reading URL or Token values.
- `spec_superflow_install_optional_mcp`: after user opt-in, registers the
  bundled stdio Server through the VS Code CLI.

It does not execute workflow commands, accept another package path, use a
registry URL, or accept URL or Token values as tool arguments.

After bootstrap, Skills execute `ssf state`, `ssf validate`, `ssf guard`, and
other CLI commands directly. The bootstrap verifies `ssf --version` against the
Plugin version and restores an existing usable CLI when an upgrade fails.

Node.js and npm are prerequisites. Installation is local to the installed
Plugin source; no second Spec repository or archive is required.

## Optional MCP with URL and Token

A local stdio MCP server can be bundled with the Plugin. `stdio` describes how
VS Code communicates with the process; it does not require the server to be a
separate installation. The Plugin starts bundled JavaScript through
`${PLUGIN_ROOT}/servers/spec-superflow-mcp-launcher.cmd`. On macOS and Linux,
the launcher falls back to the user's login shell when a GUI-launched VS Code
does not inherit the Node.js path. On Windows, Node.js must be on the system
`PATH`.

Business MCP is optional. A user who declines it still receives:

```text
workflow=READY, optionalMcp=SKIPPED
```

The CLI, Skills, planning, tests, and review workflow continue normally.

Credential configuration has a different scope:

| Configuration | Top-level server key | Interactive `inputs` |
|---|---|---|
| Agent Plugin `.mcp.json` | `mcpServers` | Starts the bundled bootstrap server; credentials are not defined here |
| User or workspace `mcp.json` | `servers` | Supported; VS Code prompts once and stores the value securely |

When the user opts in during `/workflow-init`,
`spec_superflow_install_optional_mcp` runs VS Code's `--add-mcp` command with
the bundled definition. It does not receive credentials. Registration returns:

```text
workflow=READY, optionalMcp=REGISTERED
```

To start it, run **MCP: List Servers**, select
**spec-superflow-optional-example**, and choose **Start Server**. VS Code then
prompts for the service URL and Token and keeps both values visible so users
can verify them. Neither value is written to the MCP configuration file or
passed through Chat. VS Code stores the entered values in its secure credentials
store. A later `/workflow-init` verifies the running Server and returns
`optionalMcp=READY`.

The registered definition uses the bundled
launcher and `servers/token-example-mcp.mjs`. The equivalent generated
configuration is documented under `examples/mcp/token-auth/`. Do not commit
Token values or service-specific URLs to the Plugin repository.

## Install and use

1. Run **Chat: Install Plugin From Source** in the VS Code Command Palette.
2. Enter the Git source for this complete repository.
3. Enable **Spec Superflow** in the Agent Plugins view.
4. Keep the built-in **Agent** selected, type `/workflow-init`, and select the
   Plugin-provided suggestion. Click it or press **Tab** so VS Code commits it
   as a structured Slash Command; do not send the candidate as plain text.
5. Approve CLI installation when needed.
6. Choose whether to configure the optional credentialed MCP. Skipping it
   returns `workflow=READY, optionalMcp=SKIPPED`.
7. When enabled, wait for `optionalMcp=REGISTERED`, then run
   **MCP: List Servers** and start **spec-superflow-optional-example**.
8. Complete the visible native VS Code URL and Token prompts. Run
   `/workflow-init` again to verify `optionalMcp=READY`.
9. After setup reports `workflow=READY`, select **Spec Superflow** and describe a
   requirement. Normal workflows use the installed CLI and do not install or
   upgrade it.

`/workflow-init` only prepares the runtime. It does not inspect the open
repository, create a change, or start development.

Run the setup command from the built-in **Agent** before selecting
**Spec Superflow**. This keeps the development Agent's state-machine
instructions out of the setup-only Chat request.

Run `/workflow-init` before starting a requirement. Run it again after updating
the Plugin so the CLI version is synchronized before normal workflow use.

For local Plugin development:

```jsonc
"chat.pluginLocations": {
  "/absolute/path/to/spec-superflow-plugin": true
}
```

## Target repository ownership

The Plugin is installed once and can be selected in multiple repositories.
Each target repository keeps only its own source, tests, project Skills, task
artifacts, memory, and project guidance. `project-init` writes:

```text
.github/instructions/spec-superflow.instructions.md
docs/project/project-guidelines.md
```

It leaves an existing `.github/copilot-instructions.md` unchanged. Do not copy
the central `agents/`, `skills/`, `scripts/`, or `templates/` directories into
each target repository.

## Update and verify

Update the Plugin source and keep all manifests, `package.json`, and
`/workflow-init` on the same version. Run `/workflow-init` after the update; it
detects an older CLI and requests confirmation before upgrading it.

Verify in a real VS Code Chat runtime:

| Check | Expected |
|---|---|
| Plugin | Spec Superflow is installed and selectable |
| Command | `/workflow-init` is discoverable |
| Bootstrap MCP | `spec-superflow` starts and lists the four setup tools |
| Missing CLI | Confirmation, local install, exact version, then `READY` |
| Existing version | No reinstall |
| Optional MCP skipped | `workflow=READY, optionalMcp=SKIPPED` |
| Optional MCP registered | `workflow=READY, optionalMcp=REGISTERED` |
| Optional MCP started | VS Code prompts for visible URL and Token values; bundled Server starts |
| Optional MCP verified | A later `/workflow-init` reports `workflow=READY, optionalMcp=READY` |
| Requirement entry | Uses the CLI prepared by `/workflow-init` |
| Project init | Dedicated instructions are generated; root instructions are unchanged |

Protocol tests prove server behavior but do not replace this installed Plugin
and Chat verification.

Format references: [VS Code Agent plugins](https://code.visualstudio.com/docs/agent-customization/agent-plugins)
and [MCP configuration reference](https://code.visualstudio.com/docs/agents/reference/mcp-configuration).
