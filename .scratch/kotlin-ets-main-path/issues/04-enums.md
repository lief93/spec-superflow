# Basic enums

Status: accepted (basic source enums)
Scope: spec L3, follows accepted L2
Review: deferred by user

Reference official EnumClassLowering: enum constructors keep source parameters
and gain name/ordinal; entries are stable instances; values returns a new array;
valueOf selects an exact entry or throws. Reuse language lowering for constructor
expressions and methods, shared target classes, calls and module identities.

Public CLI/JVM acceptance covers declared order, source properties and methods,
identity, cross-file returns, when and values/entries/valueOf. Collection-key
composition follows in L5; catch selection for unknown lookup follows in L6.
Per-entry subclasses remain explicitly unsupported by this round.

## Implementation

- EnumMembers emits a typed target class with original entry/property/method
  names. Constructor expressions and method bodies use LanguageLowering;
  source defaults continue through the existing official lowering.
- Lazy entry access initializes all entries in declaration order once. Failure
  becomes sticky through the shared typed try/failure nodes. This follows the
  Kotlin/JS enum accessor shape, with the spec's JVM failure oracle.
- Source enum identity/ordinal/name, values copies, stable entries, exact valueOf
  and ordinary methods work across files. Array-backed EnumEntries uses resolved
  real override links to existing List rules, not a second collection evaluator.
- Exhaustive when's official noWhenBranchMatchedException intrinsic is preserved.
- Source enum constants and methods retain names; required name/ordinal and lazy
  initialization metadata use reserved target helpers. Constructor parameters
  retain their source names after the two required metadata parameters.

## Evidence

- RED `enums/.work/run-bc9M7v`: missing IrGetEnumValue consumer.
- Official IR dump: `main-path/.work/dump-jzEDjp/ir.stdout`, including inherited
  EnumEntries -> List ownership and synthetic enum constructor/function nodes.
- First composition pass `enums/.work/run-2K9eU4`: six JVM/ETS results.
- Final `enums/.work/run-QAfmwt`: ten flat/module JVM/ETS results, strict host
  types, deterministic reversed-source output and hashes. Includes initializer
  order/laziness, defaults, values-copy isolation, stable entries, cross-file
  selection, unknown lookup and sticky repeated initializer failure categories.
  JVM/host drivers catch failures here; source try/catch remains L6.
- `/private/tmp/kotlin-ets-enums-sdk-xpTWQx`: three unchanged modules in actual
  CompileArkTS inputs; ABC/HAP produced. Not native execution.
- Equality regression `equality/.work/run-3nawID`: fifteen flat/module results.
- Self-check: source symbol ownership/imports, typed output, private construction,
  stable entry references and diff whitespace. Independent review deferred.

Limits: per-entry subclasses, complex generic Enum bases and pathological cycles
are not admitted. Map/Set consumption remains L5, not claimed by this test.
