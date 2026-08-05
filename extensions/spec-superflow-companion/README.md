# Spec Superflow for VS Code

This offline VSIX contains two independent Agent Plugins in one installation:

- the complete **Spec Superflow** Agent Plugin;
- the **Matt Engineering** Agent Plugin with source-preserved upstream Skills;
- `spec_superflow_cli_status` and `spec_superflow_install_cli` for
  `/workflow-init`;
- `spec_superflow_example_mcp_read`, a replaceable one-shot stdio MCP example.

Do not install the same Spec Agent Plugin again from Git while this VSIX is
enabled, because VS Code can otherwise discover duplicate Spec Agents.

Matt Engineering is pinned to `mattpocock/skills` commit
`2ab958093e83e0ec752e6c1c5932da465bf23e0c`, using the official manifest's 22
Skills and 66 files plus the upstream MIT license. Its approved real-host
canaries are explicit `ask-matt` and automatic `diagnosing-bugs`; all other
Skill compatibility and duplicate-name resolution remain `PENDING`. See
`docs/vscode-user-guide.md` for installation and selection steps.

## Example MCP flow

The bundled `example-mcp-reader` Skill recognizes an item URL or key and calls
only `spec_superflow_example_mcp_read`. On its first call, VS Code visibly asks
for an example service URL and Token. The URL is stored in extension state and
the Token in VS Code SecretStorage; neither is a tool argument or Chat value.

The extension then starts `servers/example-item-mcp.mjs`, performs one fixed
MCP tool call, and closes the process. The example performs no network request.
In a company fork, replace that server and the fixed tool mapping with the Jira
stdio MCP while retaining the same Skill and one-shot lifecycle.

## Build

From the repository root:

```bash
node scripts/build-vscode-vsix.mjs
```

The result is `release-assets/vscode/spec-superflow-<version>.vsix`.

Ordinary build and installation use only repository-owned files and remain
offline. Upstream changes are available only through the explicit
`scripts/sync-matt-plugin.mjs --commit <sha>` maintainer command.
