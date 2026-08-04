# Spec Superflow for VS Code

This offline VSIX contains three pieces in one installation:

- the complete Spec Superflow Agent Plugin;
- `spec_superflow_cli_status` and `spec_superflow_install_cli` for
  `/workflow-init`;
- `spec_superflow_example_mcp_read`, a replaceable one-shot stdio MCP example.

Do not install the same Spec Agent Plugin again from Git while this VSIX is
enabled, because VS Code can otherwise discover duplicate Spec Agents.

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
