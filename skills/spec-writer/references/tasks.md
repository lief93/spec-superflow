# Implementation Tasks

## Interfaces

Delete this section when no interface crosses Batch boundaries.

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

- **Why this file**: Its current responsibility and why that ownership makes it the correct change point for this AC
- **Change**: What behavior changes and what the resulting behavior becomes
- **Add**: New methods, fields, or types and their responsibilities; remove this item when none are needed
- **Reuse**: Existing components, methods, or patterns to reuse; enter `None` when none apply

##### Create `path/to/new-file.ts`

- **Why this file**: Why this responsibility needs a new file instead of an existing owner
- **Responsibility**: The new file's single responsibility
- **Add**: Main methods, fields, or types to add and their responsibilities
- **Used by**: Existing files or Batches that consume it

#### TDD Test Plan

Keep only the test layers needed to prove this AC; do not add every layer mechanically. Verify each behavior at the lowest-cost stable layer and avoid duplicate coverage. Together, the rows must cover every observable WHEN, THEN, and AND in the Scenario: Unit, Component, or Integration tests prove internal state, calls, persistence, ordering, and concurrency; UI tests prove visible state and user interaction. `Proves` must state the exact result, not merely "covers this AC." A UI row must perform the user action through a rendered control. Direct ViewModel, callback, repository, or reducer calls may only prepare state or simulate system and lifecycle events; they cannot replace the user's WHEN. Each row must identify one platform test source file and one exact test method or title. Markdown files, production source files, commands, directories, globs, and labels such as "related regression suite" are not valid Test Files.

| Layer | Platform | Action | Test File | Test Case | Proves |
|---|---|---|---|---|---|
| `Unit` / `Component` / `Integration` / `UI` | `Android` / `HarmonyOS` / `iOS` / `Web` / actual platform | `Add` / `Update` / `Run existing` / `Unavailable` | Repository-relative platform test source file; `Not configured` when unavailable | Exact test method or title; when unavailable, record where you searched and the capability gap | Observable AC result proved by the test assertions |

### Batch Verification

List commands once per Batch. Every `Add` or `Update` row above must have a real behavior-specific RED before implementation unless it characterizes existing behavior, in which case record a baseline PASS. `Run existing` rows establish a regression baseline.

- [ ] **RED / Baseline**: Run `exact focused command`; record the expected behavior-specific failure or baseline PASS.
- [ ] **GREEN**: Run `exact focused command`; all planned AC test cases pass.
- [ ] **Regression**: Run `exact affected regression command`; no related regressions.
