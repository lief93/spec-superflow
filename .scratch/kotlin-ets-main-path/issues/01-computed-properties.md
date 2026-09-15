# Top-level computed property accessors

Status: completed
Blocks: 02-file-initialization
Blocked by: none (spec approved 2026-09-15)
Review: deferred by user

## Requirement

Translate ordinary non-extension source top-level computed properties without a
backing field. Preserve getter/setter execution on every access, setter parameter
names, return values, effects, compound assignment order and cross-file ownership.

## Reuse and change boundary

Reuse Language.function/expression/arguments for bodies and calls; use ordinary
EtsFunction/EtsCall, module imports and target validation. Existing class/object
accessors and default stored top-level properties must not change.
ETS top-level accessor helpers are necessary target functions, named
__etsGet_<property> and __etsSet_<property>, with source spans. No storage/cache is
invented for a computed property. Calls bind resolved accessor symbols, not names.

## Verification

- Independent JVM oracle versus flat and multi-file CLI output.
- Repeated getter effects, setter branches, compound assignment, nullable result,
  private computed properties and original setter parameter names.
- Original member-accessor and stored-global suites remain passing.
- Stored custom accessors, delegates and extension properties remain explicit
  rejections outside this ticket. No initialization-order or native UI claim.

## Evidence

Approved for implementation. This is one sub-issue of L1,
not the complete stored-accessor/initialization requirement.

Premature exploration `tests/language/computed/.work/run-ESPVAQ` failed at the
existing top-level storage/default-accessor guard. No production change and no
acceptance pass; preserve the result without treating this ticket as claimed.

## Accepted increment (2026-09-15)

- RED `computed/.work/run-Wcc1qn`: old storage guard reproduced.
- GREEN `computed/.work/run-ZZulpa`: 54 flat + 54 module JVM/host results,
  strict types, deterministic inputs, original setter names and explicit boundaries.
- Regressions: `language/.work/accessors-TsArmk` (18 results),
  `globals/.work/run-fN8Gt7` (26 flat + module results and relocated UI callback).
- Self-check: shared function body/call/type machinery reused; no computed cache,
  no source parser, no generated-file edits. Independent review deferred.
- This completes issue 01, not L1 or the round; SDK/native not claimed.
