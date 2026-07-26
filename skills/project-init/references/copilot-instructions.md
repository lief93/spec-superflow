# Project Development Instructions

Before planning, implementing, or reviewing code, read the parts of `docs/project/project-guidelines.md` relevant to the change. First locate the matching classic implementation and its end-to-end path.

## Execution Requirements

- If `.spec-superflow/memories/MEMORY.md` exists, read the concise entry point first, then open only the topic files relevant to the task.
- Identify the input or UI entry point, event handler, state owner, data interface, model conversion, and storage boundary before making changes.
- Follow the responsibility, dependency, state, model, and reuse rules in the project baseline.
- Before adding a page, state, interface, data capability, shared component, or error-handling path, inspect the corresponding classic implementation.
- Do not invent frameworks, layers, or shared abstractions that the project does not use.
- Ask a developer to resolve conflicts between the requirement and project rules, or ambiguity about a rule's scope.

## Pre-Completion Check

- Confirm that code is placed in the correct responsibility and module.
- Confirm that dependency direction, state ownership, and model conversion follow project rules.
- Confirm that the input-to-result path and user-action-to-state-update path are complete.
- Confirm that existing project mechanisms were reused and relevant tests were run.
- Record verified, team-useful, future-reusable, non-obvious project knowledge in Shared Auto Memory when needed. Do not record personal preferences or ordinary task progress.
