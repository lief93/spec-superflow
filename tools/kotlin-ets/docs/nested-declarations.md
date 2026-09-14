# R2F declaration contract

## First implementation slice

- Non-inner source classes nested in source classes, including independent
  generic binders, constructor/property/member calls and cross-file references.
- Noncapturing local source classes, including equal names in different lexical
  scopes. Keep original source files; flatten declarations only where ETS needs it.
- Minimal deterministic emitted names for actual target binding collisions.
  Retain original class, member and parameter names otherwise.

Inner classes, captured values/type parameters, anonymous objects, secondary
constructors and expanded inheritance semantics are separate gates. Reject them
with source evidence rather than inventing constructors or dropping captures.

## Fixed shared contract

- `EtsClass.name` is the emitted binding. Optional `EtsClass.sourceName` preserves
  the original class spelling, matching the existing function contract.
- `etsClassSymbol(name, source, sourceName = name)` forms canonical IDs from the
  original name and source span. Type references, constructors, heritage and
  declarations must agree on that ID and on the emitted name.
- `EtsFile.sourcePath` owns output placement. A declaration's source span records
  provenance, not permission to change its output module. No arbitrary ID override.
- Do not rename the official source IrClass itself for target collisions. Keep
  its name and offsets; a symbol-keyed language naming table selects emitted names.
  Thus generic owner identities keep original names through the existing binder.
- Before moving classes, core records effective source linkage, including LOCAL
  scope and enclosing private declarations. Backend must not treat `!isPrivate`
  alone as authority to export a lifted local class.

## Ownership

- Main: target shared contract and tests; official common local declaration and
  popup lowering; bounded nested declaration movement and effective linkage.
- Parfit: language class naming and consumers in class declarations/references/
  types, with focused binding and module fixtures. No shared-tree/core edits
  without coordination, and no compiler build until the serial slot is granted.
- Aristotle remains the read-only review gate after writers and evidence freeze.

Official common passes own local capture/call rewriting. JS StaticMembersLowering
is the reference for nested ownership and provenance but is JS-context-specific;
do not claim its entire implementation is directly reused by the ETS backend.
Target validators retain duplicate-ID, name, type and visibility guards.

## Initial contract verification

`tests/target/ClassIdentityTest.kt` tests original identity independent of emitted
names/file ownership, duplicate identities, stale names and unknown IDs. The
pre-contract build failed as expected in `kotlin-ets-target-tests.xYShQq`;
the full target suite passed in `kotlin-ets-target-tests.w1X8UM` after the contract
change. No class lifting, language parity or native support is claimed by this
contract-only test.

## Core lowering verification

`tests/local-classes/run.mjs` compiles an immutable snapshot of the pinned core
and target sources. Baseline `run-asnmP0` rejected the legal local class because
it remained nested. `run-YfdkCV` now passes file ownership, unchanged source spans,
and effective export assertions for nested and noncapturing local classes.
Captured values, enclosing type parameters and inner classes are first checked
as legal Kotlin and then rejected by this slice with original source locations.

Capture discovery directly reuses common `ClosureAnnotator`. Placement uses common
`LocalClassPopupLowering`; the bounded nested-to-file move follows JS static
placement without importing the JS-specific backend context. Source linkage is
recorded before moving declarations. This probe does not establish generated ETS
behavior or native/SDK acceptance; those are separate evidence gates.

## Language and module verification

`tests/modules/nested-classes/.work/green-bM9IEq/result.json` records 15 original
JVM outcomes matched in both flat and three-module host execution. Eleven source
classes/interfaces retain canonical identities and generic binders; only five
actual binding collisions require fresh names, allocated by official JS NameTable.
Reverse source input order preserves module bytes. Eleven malformed typed-target
cases retain exact diagnostic locations. This is parser/host execution evidence,
not native SDK acceptance. The earlier `green-bVy9Zd` failed on a test expectation
for import quote spelling, before the corrected assertions in the passing run.

Existing regressions also pass: local-function official/JVM/host checks
`run-djfj5V`, typed language `typed-u3YIIy`, and typed inheritance `probe-HHPBKX`.
The local runner's old explicit compile list required existing target validator
dependencies; its earlier build-only failure is retained as `run-Vxz2Q6`.
Independent review remains the acceptance gate for this finite implementation.

## First review follow-up

The first review found two missing combinations: bases appended after derived
classes, and class-value bindings shadowed by source parameters. Earlier positive
results do not establish these combinations. The order regression in
`tests/local-classes/order` reproduces the old runtime failure in flat and module
output (`run-PZ9Ut3`). Same-file dependency ordering reuses the compiler's `DFS`
utility on resolved supertype symbols, after popup/static placement. Class-value
shadowing is addressed in the naming lane; final evidence/review are pending.

Follow-up evidence: order `run-8jK5ze` matches JVM/flat/modules; core `run-zFdVRA`
retains guards. Shadowing `shadow-red-NrNISv` preserves the old constructor failure;
`shadow-green-Ableh3` matches 55 JVM outcomes in each mode with lexical binding
and stable import assertions. Original `green-wl8Wgl` again matches 15 outcomes
per mode and all eleven target negatives. All are tied to current production
hashes. Both fixes now return to the same reviewer; acceptance remains pending.
