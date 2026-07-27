---
name: project-init
description: Initialize or refresh a repository's AI development baseline by inspecting real code and generating Copilot instructions plus an actionable project guideline. Invoke when the user asks to initialize project context, coding rules, architecture guidance, or canonical implementation references.
argument-hint: "[optional module or scope]"
user-invocable: true
disable-model-invocation: true
---

# Project Init

Generate a developer-reviewable project baseline from repository evidence. This is project initialization, not task planning and not project memory.

## Outputs

Write at the project root:

- `.github/instructions/spec-superflow.instructions.md`
- `docs/project/project-guidelines.md`

Use [Copilot instructions](./references/copilot-instructions.md) and [project guidelines](./references/project-guidelines.md) as the required structures. Leave an existing `.github/copilot-instructions.md` byte-for-byte unchanged. When rerunning, update the dedicated Spec Superflow instructions and generated baseline without duplicating content or discarding developer-maintained facts.

## Boundary

- Project baseline: normative technology choices, architecture ownership, coding boundaries, and canonical implementation paths.
- Task Spec: requested behavior and scenarios for one change.
- Shared Auto Memory: typed team feedback, code-invisible project context, and external references that are useful in future work; it must not duplicate the baseline.
- Build commands, progress, chat logs, task history, and generic framework advice do not belong in this baseline.

## Discovery

Inspect with a coverage goal, not a fixed file-count goal:

1. Read repository instructions and existing architecture documentation.
2. Read build/dependency configuration and enumerate top-level production modules.
3. Classify the repository: application, library, service, tool, or mixed.
4. For every applicable implementation role, inspect representative source and tests:
   - UI entry and navigation
   - event/business owner and state owner
   - public data contract and implementation
   - remote access and model conversion
   - persistence/cache and source of truth
   - dependency construction
   - shared components and reuse points
5. For an application, trace at least one complete read path and one complete user-action/write path from input to observable result.
6. For a library, trace at least one public API path from caller configuration to internal implementation and result.
7. Expand inspection when evidence conflicts or an important role remains unverified. Stop when each retained claim has evidence.

Exclude generated output, build caches, binaries, vendored dependencies, and task-local artifacts.

## Generation Rules

### Copilot instructions

Generate `.github/instructions/spec-superflow.instructions.md` with
`applyTo: "**"` frontmatter. Keep it concise and operational. Tell the agent to
read `docs/project/project-guidelines.md`, locate the relevant classic
implementation, preserve ownership and source-of-truth rules, reuse existing
mechanisms, and verify the affected path. Also tell it to read
`.spec-superflow/memories/MEMORY.md` and relevant topic links when present, and
to record only verified, non-personal, future-useful shared learnings through
`memory-manager`.

### Project guideline

Keep exactly these top-level sections:

1. `Technology And Framework Constraints`
2. `Architecture And Coding Rules`
3. `Classic Implementation Index`

Use the repository's actual terminology. Do not force ViewModel, Reducer, Repository, UseCase, or another role that the project does not use.

For each classic implementation include:

- Applies when
- Create or modify
- Implementation order
- Must preserve
- Done when
- Reference implementation

For application repositories, the implementation steps must answer where relevant:

- how remote or local data reaches UI
- how UI actions trigger business/data work
- who owns state and how UI observes updates
- where persistent, cached, session, and UI data live
- where models cross boundaries
- which existing component or abstraction is reused
- which focused tests prove the path

## Evidence Rules

- Every reference uses an existing repository-relative path and, when useful, `path#symbol`.
- A project-wide rule requires explicit documentation/enforcement or at least two consistent implementations.
- One implementation may be a classic reference, but does not by itself establish a mandatory project rule.
- Prefer current source and configuration over stale prose.
- Omit unsupported categories. Never fill space with versions, directory inventories, business fields, legacy warnings, or generic best practices.
- If removing a statement would not change implementation or review decisions, remove it.

## Existing Files

- Existing `.github/copilot-instructions.md`: leave it byte-for-byte unchanged.
- Existing `.github/instructions/spec-superflow.instructions.md`: update only
  the dedicated Spec Superflow baseline without duplicating it.
- Existing `docs/project/project-guidelines.md`: treat confirmed developer facts as authoritative; refresh generated evidence around them and report conflicts instead of silently replacing them.

## Validation

Run from the project root:

```bash
ssf project check
```

If validation fails, repair the generated documents and run it once more. Do not report completion with unresolved placeholders, missing references, or missing recipe fields.

## Output

Report:

- files created or updated
- repository type and implementation roles covered
- classic implementations generated
- validator result
- facts that still need developer confirmation
