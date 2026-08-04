---
name: workflow-init
description: Initialize, verify, or update the Spec Superflow workflow runtime without starting a Change.
argument-hint: No arguments. This command only prepares or updates the workflow runtime.
agent: Spec Superflow Setup
tools:
  - 'spec_superflow_cli_status'
  - 'spec_superflow_install_cli'
  - 'vscode/askQuestions'
---

<!-- spec-superflow-plugin-version: 0.15.0 -->

# Initialize or Update Spec Superflow

This command only prepares the global Spec Superflow CLI. It never reads the
workspace, creates a Change, configures a business MCP, or starts development.

1. Call `spec_superflow_cli_status` with no arguments.
2. Treat its JSON as authoritative. Report `READY` only when `ready` is true
   and both the Plugin and global CLI versions are exactly `0.15.0`.
3. When `requiredAction` is `request-install-confirmation`, use
   `vscode/askQuestions` to request an explicit confirmation.
4. Call `spec_superflow_install_cli` with no arguments only after an explicit
   Yes. The tool installs only from this VSIX's bundled Plugin root.
5. After installation, call `spec_superflow_cli_status` again and require the
   same exact-version `ready: true` result.
6. A refusal is `CANCELLED`. Any prerequisite, permission, PATH, rollback, or
   version failure is `BLOCKED` with the tool's recovery guidance.

Do not use terminal, file, workspace, Skill, URL, registry, package-path,
project-init, workflow-start, or Example MCP tools in this command.
