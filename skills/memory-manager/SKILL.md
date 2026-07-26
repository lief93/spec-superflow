---
name: memory-manager
description: Recall, capture, consolidate, correct, or forget Claude-style shared auto memory for spec-superflow. Invoke when prior project learnings may help a task, when the user asks to remember or forget a project fact, or when verified team feedback, project context, or an external reference may help future work.
---

# Shared Auto Memory

Maintain `.spec-superflow/memories/` as project-shared AI memory. Keep project rules, current behavior, decisions, task state, and learned context in their proper sources instead of turning Memory into a second project wiki.

## Knowledge Boundaries

- `docs/project/project-guidelines.md`: technology choices, architecture/coding rules, and classic implementations.
- `specs/<capability>/spec.md`: current business behavior and scenarios.
- `docs/adr/`: deliberate long-term technical decisions and rationale.
- Change artifacts: task scope, design, progress, evidence, and history.
- Shared Auto Memory: non-obvious information learned while working that is useful to future contributors but does not belong above.

Never duplicate another source in Memory. Link to the authoritative source when the learning depends on it.

## Storage Contract

- `.spec-superflow/memories/MEMORY.md` is a concise index. It contains only `# Project Memory`, blank lines, and entries shaped as `- [Title](topic.md) - one-line relevance hook`.
- Keep `MEMORY.md` at most 200 lines and 25,000 bytes. Keep each entry under 200 characters.
- Each topic file is a semantic topic, not a task log or module inventory. Do not pre-create categories.
- Topic files require this frontmatter:

```yaml
---
name: runtime-market-selection
description: Runtime market mapping needed when Jira requirements omit configuration details
type: project
modified: 2026-07-23
---
```

`description` is the retrieval hook. Keep it specific enough to decide relevance without opening the file. `type` must be one of:

- `feedback`: a correction or confirmed practice that clearly applies to all contributors in this project.
- `project`: project context, motivation, runtime facts, or stable caveats not stated clearly in current authoritative project sources.
- `reference`: where authoritative information lives outside the repository and when to consult it.

Private `user` memory and personal feedback are not supported in the shared repository.

## Recall

1. If `MEMORY.md` is absent, continue without Memory.
2. Read no more than its first 200 lines or 25,000 bytes.
3. Use entry hooks to choose up to five topics clearly relevant to the requirement, affected area, symptom, runtime, or external system. Read none when relevance is uncertain.
4. Treat Memory as a point-in-time observation. Before relying on a file, function, flag, behavior, or process, verify it against current code, tests, Specs, guidelines, ADRs, or the referenced external source.
5. If current evidence conflicts, trust the current evidence and correct or remove the stale Memory.

## Admission Gate

Consider saving when:

- a developer corrects a project fact or confirms a non-obvious team-wide practice;
- the reason, stakeholder constraint, runtime condition, or coordination context is absent from current code and project documentation, even if historical evidence can help verify it;
- an external project, dashboard, document, or issue source should be consulted in later tasks;
- a verified runtime, environment, or debugging conclusion is expensive to rediscover and cannot be recovered from the final code or a routine project lookup.

Save only when every condition passes:

1. **Future-useful**: likely to change a future implementation, diagnosis, verification, or coordination decision.
2. **Shared**: useful to other contributors, not a personal preference or profile.
3. **Project-specific**: not generic language or framework knowledge.
4. **Non-obvious**: not stated by an authoritative current project source and not recoverable through a routine lookup. A conclusion may qualify when reproducing it requires connecting historical evidence, current code, and runtime or review context.
5. **Verified**: supported by code, tests, reproduced runtime behavior, review evidence, an authoritative reference, or explicit developer confirmation.
6. **Stable enough**: expected to remain useful beyond the current task.

Otherwise choose `NONE`. Memory is not a required task artifact.

## Candidate-First Evaluation

Keep admission and migration proportional to the possible Memory value:

1. Read the index and proposed or legacy Memory files before inspecting repository code.
2. Apply knowledge ownership and the admission gate first. Reject module inventories, versions, commands, ordinary conventions, and task history without re-proving every line from the repository.
3. Inspect repository evidence only for a remaining candidate that could pass all conditions. Use exact candidate paths or patterns, cap search output, and read narrow matched ranges; do not search common namespaces, inventory the repository, or read broad source/build files for Memory maintenance.
4. Stop as soon as every candidate is accepted or rejected. If no candidate survives the content-level gate, return `NONE` without a repository scan.

Do not impose a fixed project file-count limit. The bound is candidate-driven: each retained topic needs enough evidence, while rejected boilerplate needs no extra discovery.
During bulk legacy cleanup, inspect final paths and `git diff --stat` or `git status`; do not print full deletion diffs unless a disputed claim requires review.

## Write Or Update

1. Capture an explicit remember/forget request or a verified correction when it occurs. At release, run one catch-up pass for signals missed during execution.
2. Read `MEMORY.md` and search existing topic names, descriptions, and content before creating a file. Update an existing semantic topic instead of creating a duplicate.
3. On the first accepted learning, run `ssf memories init` to create the empty index.
4. Use [TOPIC.md](references/TOPIC.md) as the topic structure. State the durable fact or rule, why it matters, how to apply it, and its evidence. Reference entries may replace `Why` with the external source's purpose.
   A commit may verify why a current safeguard exists, but the Memory must preserve the durable reason and application condition, not the commit chronology.
5. Set `modified` to the current date whenever substantive content changes.
6. Add or update one concise index entry. Never put memory content directly in `MEMORY.md`.
7. Run `ssf memories check` after every write, rename, migration, or deletion.

Do not create a candidate file. For shared Memory, the normal code review is the approval boundary. Ask before writing only when evidence conflicts or a code-invisible claim is unconfirmed.

## Consolidate And Promote

Consolidate when the index approaches its limits, an explicit review is requested, or a release pass finds drift:

- merge near-duplicate topics;
- remove stale or superseded statements and links;
- replace chronology with the current durable conclusion;
- keep frontmatter aligned with topic content;
- propose promotion when a learning has become an enforceable rule, current behavior, or deliberate decision.

Promotion targets are `project-guidelines.md`, a capability Spec, an ADR, or Copilot instructions. Present the promotion for developer confirmation, then remove duplicated Memory after the authoritative source is updated.

## Migrate Serena Memory

When `.spec-superflow/memories/` contains `memory_maintenance.md`, `core.md`, `tech_stack.md`, `suggested_commands.md`, `conventions.md`, `task_completion.md`, or `mem:` references without `MEMORY.md`:

1. Classify rules and architecture into `project-guidelines.md`, current behavior into capability Specs, decisions into ADRs, and task-local or quickly discoverable content for deletion.
2. Apply the admission gate to the remaining non-obvious shared learnings and rewrite only accepted items as typed topic files.
3. Create `MEMORY.md`, add one relevance hook per accepted topic, and remove Serena policy/root files and `mem:` references after their useful content is preserved.
4. Run `ssf memories check`. Never auto-convert Serena files by filename alone.

## Never Store

- personal profiles, communication preferences, or user-specific feedback;
- complete conversations, chain-of-thought, progress logs, task summaries, or failed attempts without a durable conclusion;
- ordinary code structure, file inventories, commit summaries or chronology, and facts discoverable by a routine lookup;
- current behavior already represented by capability Specs;
- coding standards, architecture ownership, classic implementations, or deliberate decisions owned by another source;
- ordinary fix recipes already evident in code and tests;
- secrets, tokens, credentials, personal data, or machine-specific sensitive values.

## Output

When Memory changes, report the topic and why it passed the admission gate. When nothing qualifies, continue silently unless the workflow requests an explicit `ADD / UPDATE / NONE` result.
