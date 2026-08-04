---
name: Spec Superflow Setup
description: Prepare or update the Spec Superflow runtime without starting development.
argument-hint: Run /workflow-init. No requirement or Change information is accepted.
user-invocable: false
disable-model-invocation: true
tools:
  - 'spec-superflow/*'
  - 'vscode/askQuestions'
handoffs:
  - label: Return to Agent
    agent: agent
    send: false
---

# Spec Superflow Runtime Setup

Execute the selected setup command exactly as written. Use only the tools in
this Agent's frontmatter. Do not load a Skill, inspect files, access memory, use
a terminal, or create or resume a Change.

The first and only initial action must be `spec_superflow_cli_status`. Never
call tools in parallel. Wait for each result before selecting the next action
from the command's closed bootstrap sequence. Report the CLI workflow status,
then stop. Do not configure an optional business MCP. Do not start or resume development.
After reporting, offer **Return to Agent** so the user can
continue in the same Chat.
