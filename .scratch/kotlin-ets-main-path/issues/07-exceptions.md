# Exception control flow

Status: focused acceptance passed
Scope: L6 common control flow and simple source exception heritage
Review: deferred

Reuse EtsTry/EtsCatch already introduced for L1 initialization, official IrTry,
and target native finally semantics. Result-position lowering must preserve source
return/break/continue, not move these into an artificial function. Standard
failures from L1/L4/L5 must share categories and catch selection. A separate finite
subcase wires simple source exception inheritance through target heritage.

## Implementation

- Official IrTry consumers produce typed EtsTry/EtsCatch and preserve result
  assignment, ordered handlers, rethrow and native finally exit semantics.
- Standard failures and simple source RuntimeException subclasses share an
  Error-backed target representation. The standard-library base declares its
  constructor/member contract to the target validator; other external heritage
  without a declaration still rejects.
- Compared the official Kotlin/JS MultipleCatchesLowering and ThrowableLowering.
  Reused official IR structure, not JS dynamic/Error runtime code wholesale.
- Statement effects remain present even when a final expression returns Unit.
  Catch rethrows retain an Error-compatible target type for arkts-limited-throw.
- Host module evaluation uses one realm, matching real modules' shared Error
  constructor rather than incorrectly allocating one realm per source file.

## Evidence

- RED run-ZnY14w: missing IrTry consumer.
- run-rc2L3L: caught a dropped Unit assignment inside try, before correction.
- Final exceptions/.work/run-PmRWRh: 8 composed JVM/flat/module results,
  strict host types, reversed input order and hashes.
- /private/tmp/kotlin-ets-exceptions-sdk-MxkHXX: actual CompileArkTS for four
  unchanged modules, ABC/HAP. No native execution claim.
- Target suite kotlin-ets-target-tests.ARernF: passed, including known external
  base constructor type checking and refusal of undeclared external heritage.
- Initialization regression .work/run-1AkVjv passed method/read/write/default,
  cross-file order, repeated failures and nested failed initialization.
- Cases include custom exception payload/message, superclass catch, nullable
  lookup and cast failures, enum lookup, exhausted collection iterator, sticky
  cross-file initialization failure, return/break/continue and finally override.

## Boundaries

Optional-message standard constructors and simple source subclasses are covered.
Throwable cause/suppressed exceptions, platform stack traces and arbitrary
external exception families are not claimed. Non-local returns across an
expression IIFE boundary remain source-linked refusals; ordinary try result
assignment/return avoids that boundary. Independent review remains deferred.
