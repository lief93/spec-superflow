# Kotlin to ETS main-path round acceptance

Status: scoped L1-L8 implementation and round acceptance complete.
Compiler revision: `69b3e00` on `andorid-to-hormony`.
Independent review: deferred by the approved spec, not passed.

## Implemented scope

| Requirement | Accepted behavior |
| --- | --- |
| L1 properties and initialization | Stored/computed accessors; first-use, once-only nonconstant file initialization; declaration/dependency order and sticky failure. |
| L2 equality | Identity, source equals/hashCode and data-class equality/hash behavior, composed with nullable/nested supported values. |
| L3 enums | Identity, order, constructor properties, methods, name/ordinal, enumeration and lookup, including failure. |
| L4 nullable types | Existing nullability paths plus supported class/interface checks/casts, single evaluation and named failures; unsupported runtime distinctions diagnosed. |
| L5 Map/Set | Common construction, lookup, mutation and traversal with object/data-class/enum/null keys, collision handling and insertion order. |
| L6 exceptions | Typed try/catch/finally in statement/result positions; ordered catches, rethrow, exit effects and shared runtime failures. |
| L7 explicit super | Resolved base calls and supported accessors with receiver/argument order and cross-file inheritance. |
| L8 interface defaults | Shared default bodies, implementing overrides, interface dispatch, inherited defaults and explicit conflict resolution. |

The numbered issue files record focused evidence, reused implementation and
bounded exclusions. No page-specific expression engine or generated ETS edits
were introduced. Original declaration/method/parameter names are retained where
the target permits; interface-default helpers are necessary target bridges,
with each source default body lowered once through the shared function pipeline.

## Frozen whole-round gate

Reproduce from the repository root:

```sh
node tools/kotlin-ets/tests/language/main-path/gate.mjs
```

Result: **15/15 stages passed**, with compiler source hashes recorded by the gate.

| Stage | Result |
| --- | --- |
| target | PASS |
| computed | PASS |
| initialization | PASS |
| equality | PASS |
| enums | PASS |
| types | PASS |
| collections | PASS |
| exceptions | PASS |
| super | PASS |
| defaults | PASS |
| numbers | PASS |
| models | PASS |
| nullability | PASS |
| type-boundaries | PASS |
| sdk | PASS |

Local generated evidence, not checked-in build artifacts:

- Gate report and per-stage stdout/stderr:
  `tools/kotlin-ets/tests/language/main-path/.work/gate-ltAWzn/report.json`.
- SDK evidence: `/private/tmp/kotlin-ets-defaults-sdk-TqD7oh`.

Behavior suites compare original Kotlin/JVM with generated flat and multi-file
ETS host execution, including results, mutations, evaluation order and supported
failure categories. The runners also check types, source-linked refusals and
deterministic module output. Default-method acceptance checks source names,
parameters, selected implementations and nonduplicated default bodies.

The SDK stage compiled three unchanged generated default-composition modules
through the actual ArkTS SDK and produced ABC and HAP outputs. This is **native
SDK compilation evidence, not ArkVM execution or device interaction evidence**.
Host differential execution is not a claim of complete native runtime parity.

## Remaining boundaries

- No full Kotlin compatibility, exhaustive standard library, complex generics,
  reflection, coroutines, multithreading or cyclic module initialization claim.
- Boxed numeric runtime discrimination and Char-to-Any distinctions remain
  explicitly unsupported rather than guessed from ETS number/string values.
- Basic enums exclude per-entry anonymous subclasses. Collections exclude full
  view/concrete-implementation coverage and mutation of stored key hash identity.
- Exceptions cover the documented standard/message constructors and simple
  source subclasses, not full cause/suppressed/stack behavior. Non-local returns
  across an unsupported expression-IIFE boundary are rejected.
- Generic interface owners with default bodies remain outside the simple forms.
- No additional Compose lifecycle, control coverage, page installation or visual
  fidelity claim belongs to this language-layer acceptance.

The implementation and test self-checks are complete. Independent review remains
deferred, separately from this passing scoped implementation acceptance.
