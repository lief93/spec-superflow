# Implementation Tasks

## Interfaces

### Batch N -> Batch M

- **Produces**: `type/function name` - how Batch M uses it

## Batch 1: [Batch objective]

Depends on: None

### AC: [Exact Scenario title from the Spec]

- **Requirement**: [Exact Requirement title from the Spec]
- **User-visible**: `Yes` | `No`

#### File Changes

Do not use line numbers. For each file, describe only the concrete change it owns for this AC. Name existing or new methods when known, but do not split every method into a separate task. If one file serves multiple ACs, repeat it under each AC with only that AC's change.

##### Modify `path/to/existing-file.ts`

- **Current responsibility**: What this file currently owns
- **Change**: What behavior changes and what the resulting behavior becomes
- **Add**: New methods, fields, or types and their responsibilities; remove this item when none are needed
- **Reuse**: Existing components, methods, or patterns to reuse; enter `None` when none apply

##### Create `path/to/new-file.ts`

- **Responsibility**: The new file's single responsibility
- **Add**: Main methods, fields, or types to add and their responsibilities
- **Used by**: Existing files or Batches that consume it

#### TDD Test Plan

Keep only the test layers needed to prove this AC; do not add every layer mechanically. Verify each behavior at the lowest-cost stable layer and avoid duplicate coverage. Together, the rows must cover every observable WHEN, THEN, and AND in the Scenario: Unit, Component, or Integration tests prove internal state, calls, persistence, ordering, and concurrency; UI tests prove visible state and user interaction. `Proves` must state the exact result, not merely "covers this AC." A UI row must perform the user action through a rendered control. Direct ViewModel, callback, repository, or reducer calls may only prepare state or simulate system and lifecycle events; they cannot replace the user's WHEN. Each row must identify one platform test source file and one exact test method or title. Markdown files, production source files, commands, directories, globs, and labels such as "related regression suite" are not valid Test Files.

| Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|
| `Unit` / `Component` / `Integration` / `UI` | `Android` / `HarmonyOS` / `iOS` / `Web` / actual platform | `Add` / `Update` / `Run existing` / `Unavailable` | Repository-relative platform test source file; `Not configured` when unavailable | Exact test method or title; when unavailable, record where you searched and the capability gap | Observable AC result proved by the test assertions |

#### TDD Steps

- [ ] **1.1 RED / Baseline: Write or update the planned tests and establish the real starting point**

```language
// Test code with exact assertions
```

**Files**: `Create/Modify: exact/path`

Run: `exact command`
Expected: For new or changed behavior, get a real behavior-specific FAIL because the behavior is not implemented. When only adding or strengthening coverage for existing behavior, record a baseline PASS. Do not manufacture RED with a sentinel or deliberate failure.

- [ ] **1.2 GREEN / Preserve: Implement the minimum code that makes the current test pass; preserve production behavior when only adding tests**

```language
// Implementation code
```

**Files**: `Create/Modify: exact/path`
**Interfaces**: Produces `name(type): returnType` - consumed by Batch N

- [ ] **1.3 Repeat real RED -> GREEN for each remaining `Add` or `Update` test, or record the baseline PASS for existing behavior**

Run: `exact command per planned test`
Expected: New or changed behavior fails before implementation and then passes; existing behavior coverage passes without an artificial failure.

- [ ] **1.4 REFACTOR: Run every planned test for the current AC and the relevant regression tests**

Run: `exact command`
Expected: PASS

- [ ] **1.5 Commit**

```bash
git add files
git commit -m "feat: description"
```
