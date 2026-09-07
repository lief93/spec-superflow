# Source-first semantic transcription

Use this policy for normal Android-to-Harmony business implementation. The goal is the same
observable behavior for the same inputs, initial state and relevant environment, not identical
syntax or a redesigned business model. Keep the existing UI/Page JSON workflow unchanged.

## Implement from source, constrain with the existing contract

Read the complete safe-snapshot callable, its state definitions and reached helpers before writing
the target method. Resolve implementations and callback ownership rather than translating names.
The existing source census supplies the coverage denominator; behavior JSON supplies explicit
constraints, evidence and source-to-target traceability. Neither replaces reading source, and
neither a populated JSON nor a scaffold proves that business code has been translated.

Keep source ownership and call boundaries recognizable unless a platform constraint requires a
change. Reuse existing action IDs and `traceability.target_implementation` entries for concrete
target symbols; tie helper/adapter details to existing data, async/lifecycle facts and slice-ledger
entries. Do not invent a programming language in JSON or require a new architecture for every app.
Do not drop reachable code as "garbage" because its purpose is unclear. Prove an exclusion from
the selected scope or leave it unresolved. User-requested improvements are separate changes.

Check only the semantic dimensions used by the scoped source:

| Source behavior | Transcription obligation |
|---|---|
| Ordered branches, early return, defaults and nullable values | Preserve branch priority and exact default/null/empty/error distinctions; do not replace `?:` with truthiness tests. |
| Mutations and external calls | Preserve which write/call happens before normal return or failure, partial state and lack of rollback. No added retries, validation, notifications or deduplication. |
| Data classes, references and collections | Check constructor vs body properties, shallow copy, equality/hash behavior, aliasing, iteration order and duplicate handling. A target spread/deep clone is not automatically Kotlin `copy()`. |
| Numbers, time and serialization | Check integer range/overflow/division, decimal precision and scale, rounding, date units/time zones and missing/null serialization. Do not route money or 64-bit IDs through JS `number` without proven compatibility. |
| Coroutines, flows and lifecycle | Preserve submission vs completion, suspension points, cancellation, error propagation and lifetime. Do not await fire-and-forget work or serialize independent work merely because calls are adjacent. Compare only ordering the source guarantees. |

For example, a Kotlin data-class property declared in the class body is not copied by generated
`copy()`. Buckwheat's `Transaction.uid` therefore resets to its initializer when copying constructor
fields. Preserve that behavior even if retaining the database ID looks more reasonable. Likewise,
a repository removal followed by a state write inside `launch` publishes only after normal return;
publishing before persistence or clearing undo state when the source retains it changes behavior.
These are examples to investigate in source, not assumptions to apply to every transaction class.

## Adapt platforms explicitly

For an unavailable API, bind the source symbol and behavior to the target adapter and document its
inputs, return/errors, effects, timing/lifetime guarantees, known differences and corresponding
tests in the existing ledger/scenarios. API names alone cannot prove equivalence. Do not fake a
Room, Coroutine, LiveData or network implementation and then report the full library as migrated.
If code is unavailable or no permitted equivalent can be demonstrated, keep that boundary
unresolved. Security/privacy constraints still apply; follow
[platform-capabilities.md](platform-capabilities.md). A necessary security change is a disclosed
departure, not an invisible "fix" that passes a parity gate.

## Verify the behavior, including defects

Start with existing Android tests: reuse their inputs, initial state and expected results. When
they are missing, run source-derived characterization cases against the original implementation
in a controlled environment. Reconcile a source/test disagreement explicitly. For the same cases,
compare returned values, resulting state, errors and external effects on Android and Harmony;
compare ordered traces only within the source's ordering guarantees. For concurrent work, examine
the relevant schedules and cancellation boundaries rather than asserting one observed total order.
Use synthetic non-sensitive data and boundary ports only where the real environment is unavailable.

A small host JVM-versus-target-logic comparison is useful early feedback, not device parity.
Record the exact original source, unchanged extracted-method spans if used, target/harness hashes,
tool versions, shared inputs, command exits and results. State precisely which adapters are real,
which are controlled ports, and what was not exercised. A decimal carried as opaque text proves
copy/transport for those cases, not decimal arithmetic. A controlled queue proves that tested
schedule, not Android coroutine dispatch or Harmony lifecycle behavior. SDK parsing/bytecode
compilation is not strict ArkTS type checking, a HAP build or device execution.

Protect material semantics with a deliberately changed target variant (for example retaining an ID
the source resets, or publishing before persistence). It must fail the same source/target
comparison. Do not modify the Android baseline or expected output to make the target pass.
Unexercised source paths remain unverified, not silently excluded from the page/flow scope.

Retain the existing source and target gates in
[behavior-contract-v2.md](behavior-contract-v2.md). Host tests may support implementation evidence
but cannot create `runtime_complete` or `application_complete`; those still require current,
scoped target/device evidence for all reviewed scenarios. Report tested semantic scope separately
from full application completeness.
