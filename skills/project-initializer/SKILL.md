---
name: project-initializer
description: Initialize or refresh spec-superflow project development rules. Invoke when the user asks to init project context, capture project coding standards, or create shared constraints for planning, implementation, and review.
---

# Project Initializer

Create `.spec-superflow/project-development-rules.md` as the shared source of project-level implementation constraints.

## Rule Scope

Record only stable rules that affect code placement, responsibility boundaries, or reuse decisions:

- Architecture boundaries: what each layer owns and must not contain.
- Reuse rules: shared components and abstractions to check before adding code.
- Project-specific rules: facts not reliably inferable from code that affect implementation or validation.

Do not record project overview, tech stack, directory inventory, build commands, conversations, process logs, or facts that can be read from code on demand.

## Initialization

1. Read project AI instructions, architecture docs, standards, and representative implementations.
2. Compare at least two similar implementations before deriving an architecture rule. Mark inconsistent patterns for confirmation instead of promoting one example to a rule.
3. Search shared components, repositories, mappers, formatters, state helpers, and base abstractions to derive reuse rules.
4. Draft rules with repository-relative evidence for every code-visible claim.
5. Ask the user to confirm the draft and add code-invisible project-specific rules.
6. Write the confirmed rules. Preserve user-maintained rules on refresh; never overwrite them silently.

## Copilot Reference

Append one reference to `.github/copilot-instructions.md` without rewriting existing content:

```text
Before planning, implementation, or review, read .spec-superflow/project-development-rules.md and treat it as project-level implementation constraints.
```

## Output

- Make every rule concrete enough to check against a design or code diff.
- Leave unsupported inferences unconfirmed.
- Start from `templates/project-development-rules.md` when the file is absent.
- Report evidence sources, items requiring manual maintenance, and the Copilot reference location.

## Exception Handling

- **Missing files or template**: create the rules file from the three required sections in this skill; do not block initialization.
- **Insufficient or conflicting evidence**: keep the item unconfirmed; do not generate a rule conclusion.
- **Parse failure or malformed existing rules**: stop, report the exact section, and preserve the original file.
- **User interruption**: preserve confirmed content; on resume, re-read the file and continue from the first unconfirmed item.
