---
name: example-mcp-reader
description: Read an item through the VSIX-bundled Example MCP bridge. Use when the user provides an example item URL or key. This is the adaptation example for a company Jira MCP.
---

# Example MCP Reader

When the user provides an item URL or key and asks to read it, call
`spec_superflow_example_mcp_read` with that exact value in `item`.

Use the returned item as source material. If the result is cancelled or
blocked, report that outcome and its reason; do not invent item content.

The tool owns credential collection and the MCP lifecycle. Never request a
credential in Chat, pass a credential as an argument, select another tool, or
replace the user's item with a guessed value.
