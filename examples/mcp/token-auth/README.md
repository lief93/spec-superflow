# Token-authenticated stdio MCP example

This example shows the user-level definition generated when a user opts into
the optional MCP during `/workflow-init`:

- `servers/token-example-mcp.mjs` is shipped with the Plugin.
- `servers/spec-superflow-mcp-launcher.cmd` starts it without assuming that a
  GUI-launched VS Code inherited the user's Node.js path.
- `spec_superflow_install_optional_mcp` registers the definition through the
  VS Code CLI.
- `user-mcp.example.json` documents the resulting user configuration and points
  to the installed server with an absolute path.
- VS Code prompts with a visible token field on first start so the user can
  verify the value, then stores it securely.

Manual fallback: replace both `<absolute-path-to-plugin>` placeholders before
using the example.
After registration, run **MCP: List Servers**, select
**spec-superflow-optional-example**, and choose **Start Server** to trigger the
native URL and Token prompts.
The server exposes
one read-only tool, `spec_superflow_token_example_status`. It returns only
whether valid URL and Token values were received, their lengths, and a short
SHA-256 Token fingerprint. It never returns either credential.

## Why the prompt is outside the Plugin config

VS Code Agent Plugin `.mcp.json` files use a top-level `mcpServers` object.
VS Code user and workspace `mcp.json` files use top-level `servers` and support
the optional `inputs` array.

In VS Code 1.123, `${input:...}` in a Plugin `.mcp.json` did not resolve from a
top-level `inputs` array. Starting the server failed instead of showing a
prompt. `/workflow-init` therefore registers a user-level definition, where
native input prompts and secure storage are supported.

The generated user definition stores the canonical installed Plugin path. Run
`/workflow-init` again after moving or reinstalling the Plugin so that an
outdated definition is replaced.

## One-shot client prototype

`one-shot-client.prototype.mjs` tests an alternative for hosts where native MCP
support is disabled. It starts the bundled stdio server, completes one MCP
handshake and tool call, then closes the server. It repeats that cold-start flow
10 times so process-exit behavior and latency are visible:

```bash
node examples/mcp/token-auth/one-shot-client.prototype.mjs
```

The prototype generates a throwaway token when no example environment variables
are set. It prints only the same length and fingerprint returned by the example
server. It does not register an MCP, change VS Code configuration, or start a
long-running gateway.
