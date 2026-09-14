# Two-batch cost observation

User priority: conserve quota; deadline pressure has eased. At most two NEW
requirements after the current R2H review. No duplicate implementation solely to
construct a benchmark. Keep the independent reviewer and test standard unchanged.

## Measurement

At dispatch and acceptance capture the last event_msg/token_count timestamp and
info.total_token_usage from each relevant local JSONL rollout. Stream parse only
these telemetry records; do not copy conversation text into evidence. Logs:

- Main: /Users/lief123/.codex/sessions/2026/05/17/rollout-2026-05-17T20-19-14-019e35e0-537e-7f22-8dc9-c3a735e9dfe3.jsonl
- Parfit: /Users/lief123/.codex/sessions/2026/09/14/rollout-2026-09-14T02-20-31-01a09bff-dbbb-70a0-98c0-41fb48c5ca27.jsonl
- Aristotle: /Users/lief123/.codex/sessions/2026/09/14/rollout-2026-09-14T12-33-58-01a09e31-7ded-72d3-a8af-60e6aeda911c.jsonl

These logs were confirmed to expose cumulative input_tokens, cached_input_tokens,
output_tokens, reasoning_output_tokens and total_tokens on 2026-09-14. Their
existing lifetime totals are NOT a baseline for the next requirement. Take fresh
start counters. On rotation/reset, preserve segments or mark totals unavailable.
Input includes cached input; output includes reasoning output. Do not double count.
Separate developer, main coordination/implementation and reviewer totals. Note
intervening user discussion or unrelated turns as attribution contamination.

Record start/end UTC, actual elapsed time, build/test wait and observed overlapping
implementation time, review iterations and rework. No invented serial comparison:
two different tasks cannot prove a causal percentage speedup. Account credits
cannot be inferred from raw tokens; cached and uncached inputs differ in cost.

## Decision

Use the first new requirement as a bounded parallel observation if its ownership
is genuinely separable. Prefer single-developer execution for the second comparable
requirement. Report a compact per-role usage/time table after each accepted batch.
If the first already shows clearly wasteful duplication, switch early. By the end
of two requirements default to single-developer serial execution unless the actual
evidence clearly supports paying for parallel overlap. No further user confirmation
is needed for that switch. Keep the fixed independent reviewer and commit/push gate.

Current state: telemetry availability verified; no prospective sample started.
R2H is already in review and is not counted as a fresh controlled observation.
