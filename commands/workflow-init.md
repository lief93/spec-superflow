---
name: workflow-init
description: Initialize, verify, or update the Spec Superflow workflow runtime without starting a Change.
argument-hint: No arguments. This command only prepares or updates the workflow runtime.
agent: Spec Superflow Setup
tools:
  - 'spec-superflow/*'
  - 'vscode/askQuestions'
---

<!-- spec-superflow-plugin-version: 0.15.0 -->

# Initialize or Update Spec Superflow

This command can initialize, verify, or update the global Spec Superflow CLI.
It is a Plugin setup command, not a development request. A Change is never an
input or output. Do not ask for a change name, requirement, scope, or
acceptance criteria. Do not inspect the workspace, read development Skills,
create task artifacts, run `ssf state init`, or start or resume the development workflow.

1. Call #tool:spec-superflow/spec_superflow_cli_status with no arguments.
2. Treat its JSON as authoritative. Report `READY` only when `ready` is true
   and both the Plugin and global CLI versions are exactly `0.15.0`.
3. If Node.js or npm is unavailable, report `BLOCKED` with the missing
   prerequisite.
4. When `requiredAction` is `request-install-confirmation`, use
   #tool:vscode/askQuestions to request an explicit confirmation.
5. Call #tool:spec-superflow/spec_superflow_install_cli with no arguments only
   after an explicit Yes. Installation must use this Plugin's bundled source.
6. After installation, call
   #tool:spec-superflow/spec_superflow_cli_status again and require the same
   exact-version `ready: true` result.
7. A refusal is `CANCELLED`. Any prerequisite, permission, PATH, rollback, or
   version failure is `BLOCKED` with the tool's recovery guidance.

Do not use terminal, file, workspace, Skill, URL, registry, package-path,
project-init, workflow-start, or optional business MCP tools in this command.
