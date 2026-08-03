---
description: Adapt the canonical semantic Reviewer to one stage-scoped OpenCode task.
mode: subagent
hidden: true
---

# OpenCode Review Invocation

The initial invocation is a fresh independent review. A resumed same-stage
re-review may retain its Reviewer context, but every invocation must reread the
exact current candidate, supplied stage inputs, and current repository evidence
with ordinary project-read and terminal tools, then complete the entire
applicable Review Focus.
Earlier findings, verdicts, and candidate contents are history, not evidence
for the current verdict. Follow the appended canonical Reviewer contract
exactly and return the exact unfenced JSON result to the Primary task.
