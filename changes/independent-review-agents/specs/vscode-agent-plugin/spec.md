## MODIFIED Requirements

### Requirement: VS Code and OpenCode register the same review topology

VS Code and OpenCode SHALL register one visible Primary and one hidden fixed
Reviewer. Reviewer SHALL use the host's ordinary project-read and terminal tools
for repository inspection while remaining behaviorally read-only. Explicit
`/workflow-init` SHALL remain the only bootstrap route, and ordinary workflow
requests SHALL call the global `ssf` directly without bootstrap checks.

#### Scenario: Plugin host resolves review capabilities

- **WHEN** the repository or packed Plugin configuration is loaded
- **THEN** the Primary SHALL be able to invoke only the fixed Reviewer for semantic review
- **AND** Reviewer SHALL be able to read project files and run read-only SCM inspection without a custom command allowlist or dedicated SCM tool
- **AND** Reviewer SHALL be prohibited from editing, mutating Git, executing tests or workflow commands, changing state, calling MCP, or invoking another Agent
- **AND** bootstrap MCP permissions SHALL remain isolated to `/workflow-init`
