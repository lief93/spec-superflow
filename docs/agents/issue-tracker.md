# Issue tracker: Local Markdown

Engineering specs and tickets for this repository live under `.scratch/`. The GitHub remote is not used for workflow state unless the user explicitly authorizes external issue writes.

## Conventions

- One effort per directory: `.scratch/<feature-slug>/`.
- The synthesized spec is `.scratch/<feature-slug>/spec.md`.
- Implementation tickets are one file each under `.scratch/<feature-slug>/issues/<NN>-<slug>.md`.
- Tickets are numbered in dependency order and declare their blocking edges.
- A ticket whose blockers are complete is on the frontier and may be assigned to the persistent development task.
- `Status:` records `ready-for-agent`, `claimed`, `completed`, or a canonical triage role.
- Decisions and evidence are appended to the owning ticket; do not create remote issues, commits, or pushes without explicit authorization.

## Skill operations

When a Matt workflow skill says to publish, fetch, claim, or resolve a ticket, read or update the corresponding local Markdown file. Work one requirement at a time through the persistent development task. The project manager accepts intermediate seams and ticket granularity; the user performs final project acceptance.

## Persistent task callback contract

- Every dispatch supplies the project-management task ID.
- Before emitting its own final response, Dev or Reviewer must explicitly call the native `send_message_to_thread` tool with the completion, blocker, or verdict addressed to that management task.
- The sender must verify that the tool result returns the same target task ID. A final response written only inside the worker task is not a callback and does not complete the handoff.
- Ordinary progress stays inside the worker task; only completion, a genuine blocker, or a review verdict is sent back.
