# VS Code Agent Plugin

The VS Code Agent Plugin is the centrally installed delivery unit for
spec-superflow. It contributes the selectable **Spec Superflow** agent and the
maintained workflow skills. The globally installed `ssf` CLI is the
deterministic workflow runtime and is maintained at the same version as the
Plugin.

## Runtime Model

```text
VS Code user profile
  spec-superflow Agent Plugin
    agents/                 selectable workflow agent
    skills/                 centrally maintained workflow skills
    scripts/                centrally maintained deterministic helpers
    templates/              centrally maintained artifact templates
    .mcp.json               optional centrally maintained MCP servers

Global command
  ssf                       workflow runtime and user-facing CLI entrypoint

Business repository
  .github/copilot-instructions.md
  .github/instructions/     repository-owned rules
  .github/skills/           repository-owned skills
  changes/                  generated change artifacts
  .spec-superflow/          shared memory
  application code
```

The plugin and repository customizations are additive. Repository instructions
and repository-owned skills remain local to the open workspace. Avoid using the
same skill name for a central skill and a repository skill. The Spec Superflow
agent links its maintained Skills directly, while deterministic helper commands
run through the global `ssf` CLI. It does not run `ssf inject`; the selected
agent handles workflow routing without replacing the repository-owned Copilot
instructions file.

## Install From an Internal Git Repository

1. Install the matching `ssf` CLI globally and verify it with `ssf --version`.
2. In VS Code, run **Chat: Install Plugin From Source**.
3. Enter the internal Git URL for this repository.
4. Verify the plugin under `@agentPlugins @installed`.
5. Select **Spec Superflow** from the agent picker when the workflow is needed.
6. Switch back to another agent to stop applying the Spec Superflow agent
   instructions. No other agent needs to be removed.

The plugin is installed once in the user's VS Code profile and is available in
multiple repositories.

`ssf doctor` checks a spec-superflow source checkout and is intended for
workflow maintainers. It is not an installation check for business
repositories.

## MCP Template

`.mcp.json` intentionally contains an empty `mcpServers` object until the team
defines a real server, executable, ownership model, and security policy.

Add a server only after its command and configuration are known:

```json
{
  "mcpServers": {
    "company-service": {
      "command": "company-mcp-server",
      "args": ["--stdio"],
      "env": {
        "COMPANY_ENV": "${input:company-environment}"
      }
    }
  }
}
```

Prefer a command installed and versioned by the company. Do not commit tokens
or machine-specific credentials. Plugin MCP servers start whenever the plugin
is enabled, not only when the Spec Superflow agent is selected.

## Ownership

| Content | Location | Owner |
|---|---|---|
| Workflow agent and state-machine skills | Agent Plugin | Workflow maintainers |
| Shared business skills | Agent Plugin | Domain maintainers |
| MCP definitions | Agent Plugin | Platform maintainers |
| Architecture and coding rules | Business repository | Repository maintainers |
| Repository-specific skills | Business repository | Repository maintainers |
| Change artifacts, evidence, and memory | Business repository | Change owner and reviewers |

## Verification

Test the installed plugin in at least two unrelated repositories:

1. The same **Spec Superflow** agent appears in both agent pickers.
2. Selecting another agent does not apply the Spec Superflow agent
   instructions.
3. Repository-specific instructions and skills differ correctly by workspace.
4. The agent loads Skills from the installed Plugin and executes helper
   commands through global `ssf` while the repository contains no central
   runtime files.
5. Generated artifacts remain in the target repository.
6. Existing `.github/copilot-instructions.md` content remains unchanged.
7. Chat customization diagnostics show only the intended central
   spec-superflow plugin as the workflow source; if an old project copy remains,
   the selected agent still opens skills through its explicit central registry.
