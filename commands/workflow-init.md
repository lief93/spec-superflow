---
name: workflow-init
description: Verify the Spec Superflow runtime bundled with this Plugin.
---

<!-- spec-superflow-plugin-version: 0.14.0 -->

# Initialize Spec Superflow

This is a Plugin setup command, not a development request. Follow this command
directly instead of the Agent's `workflow-start` route. Do not inspect the open
workspace, read development Skills, create task artifacts, or start the
development workflow.

Call the `spec_superflow_health` tool supplied by the bundled Plugin runtime.

Report:

- `READY` when the tool reports `status: ready`, `runtime: bundled`, and version `0.14.0`.
- `BLOCKED` when the tool is unavailable, the runtime is not bundled, or the
  reported version differs. Include the failed check and recommend reinstalling
  or updating the Plugin from its configured source.

Do not install a package or modify the open workspace.
