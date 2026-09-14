# R2G local class value captures

## Acceptance

2026-09-14: fixed reviewer Aristotle passes requirements and code quality after
the capture-parameter naming correction; main accepts this finite subset.
`shadow-green-xtyLVs` matches 15 original JVM outcomes in flat and module output,
including both exact reviewer repros and imported helpers. `green-I5AG8s` matches
30 outcomes per mode with eight malformed-IR rejections. Both manifests match all
48 final production hashes; LanguageLowering SHA-256 is
`811609674c8517ac016969e03674e548b377f99c6c1ac8390e687dd4dbb1d4ba`.
Shadow RED `shadow-red-h3o8XO` retains the original failure. These are host
semantic/contract tests, not ArkTS SDK/native or whole-R2 acceptance.

## Finite contract

- Named local classes with one primary constructor, no non-Any supertype, and
  value captures representable by existing language types. Cover immutable values,
  mutable shared cells and source objects. Do not copy mutable captured values.
- Official ClosureAnnotator, SharedVariablesLowering and LocalDeclarationsLowering
  own discovery, boxing, capture arguments, rewritten uses and constructors.
- Preserve original class/method/parameter names and spans. Generated capture
  parameters/fields may require distinct target names by symbol identity. Do not
  rename source bindings or accept arbitrary fields because their name looks generated.
- Only exact official capture-field origins in owned local classes authorize
  direct target fields. Existing EtsField/EtsMember/typed constructor nodes suffice;
  no raw-text node, untyped escape, new expression engine or validator bypass.
- Official capture initialization precedes Any delegation in IR. Consume those
  assignments in their existing order; Any has no emitted superclass call.
  Do not relax constructor order for arbitrary statements or derived classes.
- Source locations for official synthetic capture initialization derive from its
  owning field/class, rather than guessing another source statement.

Captured outer type parameters, inner/anonymous classes, secondary constructors,
and captures combined with non-Any supertypes still reject with source locations.
Keep those boundaries distinct from successfully implemented value captures.

## Ownership and checks

- Main: core eligibility and pinned official IR proof; guard regression fixtures.
- Parfit: language capture-field identity/names and constructor consumer, plus
  JVM versus flat/modules tests for independent instances, shared mutation,
  constructor/default argument order, object captures and lexical name collisions.
- Same Aristotle review after frozen implementation and focused checks; main
  acceptance precedes another increment. Builds serialized; no native subcycle.

Reference: pinned Kotlin 2.1.20 common LocalDeclarationsLowering creates capture
fields with DECLARATION_ORIGIN_FIELD_FOR_CAPTURED_VALUE and prefix initializer
statements with STATEMENT_ORIGIN_INITIALIZER_OF_FIELD_FOR_CAPTURED_VALUE. Reuse
these identities, not origin-name strings.

## Core evidence

`tests/local-classes/.work/run-hbDF4a` reproduces the earlier blanket value-capture
rejection. `run-mKHYaN` passes after the eligibility change: three value-capture
classes have official capture fields linked to constructor parameters; mutable
capture keeps the exact ETS shared-cell class identity. Original ownership and
spans remain intact. Captured generic binders, derived captured classes and inner
classes still fail with source evidence. This core probe does not establish ETS
behavior; language consumption and JVM/target parity are pending.

## Language evidence awaiting review

The frozen language lane passes `captures/.work/green-fEhNxA`: 30 original JVM
outcomes match flat and three-module ETS host execution. Six local classes and
seven capture fields retain typed field/member/constructor identities. Eight
source-linked malformed-IR cases reject; generated-name collisions preserve source
bindings. The actual prior consumer rejection is retained in `red-9bnwut`.
The existing noncapturing nested suite `green-rHTaeq` also passes. These manifests
match current production hashes; independent review is still required.

The first review requested generated capture-parameter naming against visible
emitted function bindings, including overload names. Existing source-constructor
collision tests alone do not prove that combination. Both JVM-valid reviewer
examples are retained at `/tmp/kotlin-ets-r2g-review.HIHw0O`; a focused fix and
JVM/flat/module regression are in progress before re-review.
