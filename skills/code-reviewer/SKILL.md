---
name: code-reviewer
description: Review completed implementation batches for spec compliance and code quality. Invoke after execution batches complete, before merging, or when a review gate is reached in the workflow.
---

# Code Reviewer

Two responsibilities: requesting review (dispatching a reviewer subagent) and receiving review (acting on feedback with technical rigor). **Review early, review often. Verify before implementing feedback.**

## Part 1: Requesting Review

**Mandatory after**: each task in SDD, each major feature, each execution batch, before merge.
**Optional**: when stuck, before refactoring, after fixing complex bugs.

### Procedure
1. Get SHAs: `BASE_SHA=$(git rev-parse HEAD~1)` and `HEAD_SHA=$(git rev-parse HEAD)`
2. Read project-root `specs/<capability>/spec.md` for each affected capability. Read `docs/project/project-guidelines.md` and the classic implementation selected by the design/contract when configured. If `.spec-superflow/memories/MEMORY.md` exists, read its entrypoint and only linked topics relevant to the diff.
3. Dispatch an independent `general-purpose` reviewer subagent using `skills/code-reviewer/code-reviewer-prompt.md`.
4. Fill placeholders: `[DESCRIPTION]`, `[PLAN_OR_REQUIREMENTS]`, `[PROJECT_BASELINE]`, `[PROJECT_MEMORIES]`, `[CAPABILITY_SPECS]`, `[BASE_SHA]`, `[HEAD_SHA]`.
5. Act on feedback: fix Critical immediately, fix Important before proceeding, note Minor for later, push back with reasoning if reviewer is wrong.
6. Create or update `<change-dir>/pr-summary.md` from `templates/pr-summary.md`. Record delivered scope, verification evidence, exceptions, and known risks. Preserve the contract's frontend classification and planned UI/Device obligations; implementation-time UI results may be added now, while release-archivist records the fresh final UI regression and Device Test evidence.
7. If review and the resulting fix establish a reusable non-obvious project learning, invoke `memory-manager`; ordinary review findings stay in the review/PR artifacts.

## Part 2: Receiving Review Feedback

### The Response Pattern
1. READ feedback without reacting
2. UNDERSTAND and restate requirement
3. VERIFY against codebase reality
4. EVALUATE: technically sound for THIS codebase?
5. RESPOND: technical acknowledgment or reasoned pushback
6. IMPLEMENT: one item at a time, test each

### Severity Levels

| Level | Meaning | Action |
|-------|---------|--------|
| Critical | Bugs, security, data loss, broken functionality | Fix immediately |
| Important | Architecture problems, missing features, poor error handling, test gaps | Fix before next batch |
| Minor | Code style, optimization, documentation polish | Note for later |

### Forbidden Responses
Never: performative agreement ("You're right!", "Great point!"), blind implementation before verification, thanking the reviewer. Instead: restate the requirement, ask clarifying questions, push back with reasoning, or just fix it (actions > words).

### Handling Unclear Feedback
If any item is unclear → STOP. Do not implement anything yet. Ask for clarification on unclear items. Partial understanding = wrong implementation.

### Source-Specific Rules

**From user**: Trusted — implement after understanding. Still ask if scope unclear. No performative agreement.

**From external reviewer**: Before implementing, check: technically correct for this codebase? breaks existing functionality? reason for current implementation? works on all platforms? reviewer understands full context? If suggestion seems wrong, push back with technical reasoning.

### When to Push Back
Suggestion breaks existing functionality, reviewer lacks context, violates YAGNI, technically incorrect for this stack, legacy/compatibility reasons, conflicts with user's architectural decisions. Push back with technical reasoning, not defensiveness.

### Implementation Order
1. Clarify unclear items first
2. Fix blocking issues (breaks, security)
3. Fix simple issues (typos, imports)
4. Fix complex issues (refactoring, logic)
5. Test each fix individually, verify no regressions

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Performative agreement | State requirement or just act |
| Blind implementation | Verify against codebase first |
| Batch without testing | One at a time, test each |
| Assuming reviewer is right | Check if breaks things |
| Avoiding pushback | Technical correctness > comfort |
| Partial implementation | Clarify all items first |

## Exception Handling

- **Parse failures**: Report specific file, request regenerated review package
- **Missing files**: Regenerate via `scripts/review-package`. Empty diff = nothing to review
- **User interruption**: Re-read review report on resume, continue from next unreviewed batch
