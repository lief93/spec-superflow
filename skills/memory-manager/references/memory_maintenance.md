# Memory Maintenance

## Discovery Model

- Discover memories progressively through references; do not load every memory into each task.
- Initially list memory names only, then read `mem:core` as the graph root.
- `mem:core` points to focused memories for major project domains. Focused memories may reference more specific memories when project complexity requires another level.
- Use topics and folders to make structure explicit. Topics may mirror modules or stable domains such as architecture and debugging.
- Write references inside backticks with the `mem:` prefix. Surrounding text must explain what the target contains and when it is relevant.
- The referring memory explains when to read a target; the target itself contains only its project knowledge.

## Style

- Write dense agent notes, not prose documentation.
- Prefer invariants and terse bullets.
- Exclude obvious background, rationale, and examples unless they prevent a likely mistake.
- Keep guidance durable, generalizable, and independent of a single task.

## Add Or Update Threshold

Add or update a memory only with stable, non-obvious project knowledge that avoids complex rediscovery in future tasks.

Do not add quick-read facts, generic language or framework knowledge, one-off task notes, volatile line-level details, or behavior likely to change soon.

## No-MCP Storage

- `mem:<name>` resolves to `.spec-superflow/memories/<name>.md`.
- Rename or move a memory only when every marked reference is updated in the same change.
- Run `ssf memories check` after initialization, renaming, deletion, or maintenance.
