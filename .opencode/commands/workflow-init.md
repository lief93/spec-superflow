---
description: Initialize or update the Spec Superflow workflow runtime.
agent: spec-superflow-setup
subtask: true
---

# Initialize or Update Spec Superflow

This command prepares the workflow runtime in its hidden setup subagent. Its
configured permissions provide the status/install bootstrap tools and user
confirmation, while workspace, Skill, terminal, and development actions remain
with the primary Agent.

1. Call `spec_superflow_cli_status`.
2. If the result reports `ready: true`, report `workflow=READY` and stop.
3. If installation or upgrade is required, ask the user for explicit
   confirmation.
4. Only after confirmation, call `spec_superflow_install_cli` without
   arguments.
5. Call `spec_superflow_cli_status` again.
6. Report `workflow=READY` only when the fresh result reports `ready: true` and
   the CLI version exactly matches the Plugin version.
7. If the user declines, report `CANCELLED`. If installation, permissions,
   PATH, rollback, or version verification fails, report `BLOCKED` with the
   returned recovery guidance.

End the setup turn after the reported outcome. A later user request begins the
ordinary workflow in the primary Agent.
