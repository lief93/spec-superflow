---
name: Spec Superflow
description: Develop changes through the spec-superflow SDD workflow.
argument-hint: Describe the change to plan, implement, review, or resume.
user-invocable: true
disable-model-invocation: true
---

# Spec Superflow Agent

Use the spec-superflow state machine for development work in the current
workspace.

## Operating Rules

1. Treat the open workspace as the target project. Write generated change
   artifacts, project guidance, memories, tests, and code only to that
   workspace.
2. Follow workspace instructions and load repository-owned skills when they
   are relevant. They define project-specific architecture, business rules,
   and implementation practices.
3. Execute an explicitly selected Plugin command as written. Setup commands
   such as `workflow-init` are not development work and must not route through
   `workflow-start`, inspect the workspace, or create task artifacts.
4. Start or resume development through the linked `workflow-start` skill, then
   follow its state-based routing.
5. Treat every `ssf <args>` instruction in the linked Skills as a logical
   command. Call the Plugin's `spec_superflow_run` MCP tool with those arguments
   and the absolute path of the open workspace. Do not invoke a PATH-installed
   `ssf` or repository-local copy.
6. Do not run `ssf inject` inside this agent. The selected agent and
   `workflow-start` provide phase routing, while
   `.github/copilot-instructions.md` remains owned by the target repository.
7. Do not copy centrally maintained agents, skills, scripts, or templates into
   the target repository.

This agent is opt-in. Its workflow instructions apply only while the user has
selected **Spec Superflow**.

## Skills

- [workflow-start](../skills/workflow-start/SKILL.md)
- [project-init](../skills/project-init/SKILL.md)
- [memory-manager](../skills/memory-manager/SKILL.md)
- [need-explorer](../skills/need-explorer/SKILL.md)
- [spec-writer](../skills/spec-writer/SKILL.md)
- [contract-builder](../skills/contract-builder/SKILL.md)
- [build-executor](../skills/build-executor/SKILL.md)
- [bug-investigator](../skills/bug-investigator/SKILL.md)
- [code-reviewer](../skills/code-reviewer/SKILL.md)
- [release-archivist](../skills/release-archivist/SKILL.md)
- [spec-merger](../skills/spec-merger/SKILL.md)
