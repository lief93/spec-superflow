# Known Risks

## Pending VS Code Runtime Evidence

The local verifier does not automate the GitHub Copilot Chat host. Command
discovery, command execution, terminal approval UX, rendered `READY`, and a
second Chat invocation remain pending until the final Plugin is exercised in a
real VS Code runtime.

## Production MCP Not Configured

The production `.mcp.json` intentionally contains no server. A company-approved
MCP runtime, tool discovery, and tool call remain `Not Configured`. The
repository fixture is not production evidence.

## Internal Project Validation

Company business Skills, ordinary internal requirements, and HarmonyOS device
flows are outside this local remediation. `docs/internal-validation-prompt-zh.md`
keeps those checks explicit without marking them as passed.
