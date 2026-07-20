---
name: memory-manager
description: Initialize, read, and maintain spec-superflow project memories without Serena or MCP. Invoke when the user asks to initialize project memory, when a workflow needs relevant long-term project knowledge, or after a verified change may have produced reusable project knowledge.
---

# Memory Manager

Maintain `.spec-superflow/memories/` as a progressive graph of durable project knowledge. Use ordinary file listing, search, reading, and editing; do not require Serena, MCP, or a language server.

## Storage Contract

`mem:<name>` maps to `.spec-superflow/memories/<name>.md`.

Required policy:

- `.spec-superflow/memories/memory_maintenance.md`

Initial project memories:

- `core.md`: graph root, source map, and project-wide invariants that do not belong in a focused memory.
- `tech_stack.md`: technologies and version pins only where they constrain implementation.
- `suggested_commands.md`: project-specific development and verification commands plus prerequisites.
- `conventions.md`: stable codebase-specific naming, architecture, and design patterns.
- `task_completion.md`: checks required before a coding task is considered done.

Create `<topic>/core.md` only for a distinct module or domain with stable, non-obvious invariants that would otherwise require complex rediscovery. A directory or module alone does not justify a memory.

## Initialize

1. Create `.spec-superflow/memories/memory_maintenance.md` from the `references/memory_maintenance.md` file beside this Skill if absent. Preserve an existing policy.
2. Read the policy before inspecting or writing other memories.
3. Inspect project instructions, architecture docs, build configuration, dependency manifests, and representative implementations with targeted reads.
4. Bound discovery before generating memories:
   - List names and sizes before reading bodies; exclude generated output, caches, binaries, and vendored dependencies.
   - Search for relevant terms first. For files over 300 lines, read headings and matched ranges instead of the entire file.
   - Start with one or two representative implementation files per architectural role. Expand only when evidence conflicts or a durable claim remains unsupported.
   - Default budget: at most 12 repository-read commands and 1,500 displayed lines. Cap search output and snippets explicitly. If the budget cannot support a claim, omit it and report the gap instead of scanning broadly.
   - Stop when each proposed memory claim has a repository source; initialization is a map, not a full code review.
5. Generate the five initial project memories. Keep cheap-to-rediscover module names in `core`; create focused memories only when the admission threshold is met.
6. Ask the user only for stable runtime or platform facts that code cannot reveal. Do not block initialization when none are needed.
7. Add one non-duplicated project instruction:

```text
At task start, list .spec-superflow/memories, read memory_maintenance and core, then follow only mem: references relevant to the task. Before completion, evaluate verified findings with memory-manager.
```

8. Run `ssf memories check` and report generated names, unresolved references, and unverified facts.

## Read For A Task

1. List memory names without loading their bodies.
2. Read `memory_maintenance`, then `core`.
3. Infer affected modules and topics from the requirement and repository.
4. Follow only relevant `mem:` references. Stop when enough constraints are known to plan or execute safely.
5. Keep current behavior in project-root `specs/<capability>/spec.md`; Memory supplements implementation knowledge and does not replace Spec.

## Maintain After A Change

Run only after implementation, tests, and review establish the final result.

For each finding, choose `ADD`, `UPDATE`, or `NONE`:

- `ADD`: stable, non-obvious, useful across future tasks, and expensive to rediscover.
- `UPDATE`: an existing memory is incomplete or stale; replace the current conclusion rather than append task history.
- `NONE`: task-local, generic, volatile, easily read from code/tests, or already represented.

Use the final diff, tests, review findings, and verified runtime behavior as sources. Do not create a candidate document. Memory edits travel in the normal PR; ask the developer only when a fact is code-invisible, contradictory, or unverified.

After editing, update `core` or topic references where discovery changed and run `ssf memories check`.

## Quality Rules

- Read `memory_maintenance.md` before every write or structural change.
- Operational instructions for the current client or workflow are not project facts.
- Write dense agent notes: invariants and terse bullets, not prose reports.
- Do not save task history, chat, progress logs, failed attempts, generic framework knowledge, file inventories, or volatile line-level details.
- Do not describe a command as verified unless it ran successfully; record necessary permissions, devices, variants, or environment prerequisites.
- Do not overwrite user-maintained or conflicting facts silently.

## Exception Handling

- Missing policy: recreate it from the template before continuing.
- Broken `mem:` reference: repair the reference or restore the target; do not ignore it.
- Conflicting evidence: preserve the current memory, report the conflict, and request a decision.
- Interrupted maintenance: re-read current files and final change evidence before resuming.
