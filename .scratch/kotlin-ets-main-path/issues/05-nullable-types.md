# Nullable values and runtime types

Status: focused acceptance passed
Scope: spec L4, follows L3
Review: deferred by user

Reuse the existing official expected-value visitor, typed type operators and
source properties/functions. Verify nullable models, safe calls/Elvis, casts,
interfaces and !! through the public CLI. Missing boxed scalar distinctions must
stay explicit diagnostics, never inferred from a shared ETS number type.
Source catch composition remains the dependent L6 gate.

## Implementation and evidence

- Source interfaces carry stable qualified membership tags; classes include inherited
  memberships. Checks evaluate their operand once and do not use interface instanceof.
  Mirrors the runtime-metadata boundary in official Kotlin/JS TypeOperatorLowering.
- Official CHECK_NOT_NULL consumes a typed value, preserves single evaluation and
  raises NullPointerException. Null throwing casts raise NullPointerException;
  incompatible non-null casts raise ClassCastException. Source catch matching is L6.
- Official AbstractValueUsageTransformer marks unsupported Char-to-Any boxing;
  numeric runtime discrimination remains a source-linked rejection, not JS typeof number.
- SDK exposed es2abc's parsing failure for typed IIFEs after `as` in conditionals.
  The target printer omits redundant IIFE return annotations (not target tree types).
  Ordinary functions/callback annotations remain; target precedence test added.
- `tests/language/types/.work/run-4By2D7`: 10 JVM/host results, flat/modules,
  strict host types, source input hashes, deterministic reversed-source modules.
- `/private/tmp/kotlin-ets-types-sdk-uSXDmV`: actual CompileArkTS, three unchanged
  generated modules, ABC/HAP. This is compile evidence, not ArkVM execution.
- `tests/language/types/.work/rejections-TzeqCn`: Char boxing and numeric runtime
  type checks refuse with source line/column and do not write ETS output.
- `tests/nullability/.work/run-KIbdbN`: 57 JVM/host results and three frontend
  rejection boundaries on final production sources.
- Target suite `kotlin-ets-target-tests.dcTONK` passed including printer, interfaces,
  inheritance and exception target contracts. Diff self-check passed; review deferred.
- Failed host and SDK runs remain under .work and /private/tmp as reproduction evidence.
  L5 nullable collection composition and L6 catch composition remain round-level gates.
