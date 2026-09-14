# Source Library Inlining

This slice acquires dependency function bodies by compiling explicitly supplied
Kotlin source files in the same official FIR2IR session as the application. It
does not load binary library bodies from JVM signatures, decompile bytecode, or
generate replacement bodies for named APIs such as `repeat` or `let`.

## Official Reuse

`src/core/LibraryInlining.kt` uses the real `JvmBackendContext` assembled for the
same frontend artifact and directly invokes these Kotlin 2.1.20 implementations:

| Implementation | Responsibility |
| --- | --- |
| `org.jetbrains.kotlin.ir.inline.CommonInlineCallableReferenceToLambdaPhase` | Prepare callable references for selected inline calls. |
| `org.jetbrains.kotlin.ir.inline.FunctionInlining` | Copy actual IR bodies, substitute type/value parameters, evaluate arguments/defaults, and inline eligible lambda bodies. |
| `org.jetbrains.kotlin.backend.common.lower.ReturnableBlockTransformer` | Replace block-target returns with ordinary blocks, or result variables plus `do-while(false)`/`break` when early exits require them. |

The small `InlineFunctionResolver` subclass only selects real, non-external,
inline declarations with bodies whose `IrFile` belongs to the explicit source
module. It does not implement inline semantics. The new stage runs inside the
frontend lifecycle before the existing official string-concatenation pass; the
target callback sees compiler IR while the project remains alive.

The official inliner produces `IrInlinedFunctionBlock`, which preserves the
original function symbol, library file entry and declaration offsets. Ordinary
block normalization retains those nodes and their provenance. No JavaScript
intermediate is used. No Language/target-tree/printer/validator changes belong to
this slice.

## Source Versus Binary

The test builds `InlineLibrary.kt` into a real JVM dependency JAR. The JVM oracle
compiles the application against that JAR without the library source. The ETS
CLI instead explicitly receives `Application.kt`, `LocalInline.kt` and the same
`InlineLibrary.kt` source, then the official frontend resolves cross-file calls.
The recorded source hashes and JAR hash identify both inputs. This proves a real
built library's **source route**, not binary IR body loading.

An ordinary JVM JAR may expose an inline declaration, parameter types and Kotlin
metadata without an `IrBody`. `JvmIrDeserializerImpl` only deserializes JVM IR
when the binary header actually contains `serializedIr`; it is not a general
bytecode-to-IR converter. `NonLinkingIrInlineFunctionDeserializer` requires
`KlibDeserializedContainerSource` and serialized KLIB bodies, and intentionally
creates some unbound symbols for later linkage. Neither facility is claimed to
be integrated for arbitrary binary dependencies here.

Bodyless external inline calls are recorded, not eagerly rejected: UI/stdlib
adapters retain the opportunity to handle supported calls. If the target callback
rejects a recorded call at its source span, the diagnostic additionally explains
that no inline IR body is loaded and explicit dependency source is required.
The original diagnostic is retained. An unavailable body never becomes a guessed
target call or invented implementation.

## Tests

```sh
node tools/kotlin-ets/tests/inline/run.mjs
```

Every run uses a fresh `tests/inline/.work/run-*` directory and records commands,
exit codes, stdout/stderr, a real built library JAR and hashes, actual production
IR, and independent JVM/ETS runtime results. Coverage includes cross-file inline,
two changed inputs, named-argument source evaluation order, omitted defaults,
captured mutable variables, multiple callback invocations and library-local early
returns. The binary-only negative must give source offsets and no target output.

The actual-IR acceptance condition is non-vacuous: the frontend callback must
contain no remaining source-inline calls, non-zero official inline blocks linked
to the actual source declaration/file/offsets, and no remaining returnable blocks.
The binary probe separately verifies a signature resolved from the built JAR has
no IR body, without making the frontend reject an otherwise successful callback.

RED `.work/run-VojgNb`: the dependency build and four JVM oracle values succeeded,
but the production frontend retained four resolved source inline calls. This is
the agreed real-IR transformation RED, not a missing compiler/tool failure.
Initial core evidence `.work/run-yqloRD`: zero source-inline calls, ten official
inlined blocks (three from the real library file), zero returnable blocks. Its
CLI step was blocked by unrelated concurrent generic compiler errors, so it is
not recorded as end-to-end GREEN.

### Completed Regression Evidence

All three commands below exited 0 on 2026-09-13 after the shared language/type
compilation fixes. Paths are relative to `tools/kotlin-ets/`.

| Command (from repository root) | Evidence directory | Actual result |
| --- | --- | --- |
| `node tools/kotlin-ets/tests/inline/run.mjs` | `tests/inline/.work/run-EvxPbl` | Four public CLI/ETS values equal the independently compiled JVM application using the built library JAR; zero source-inline calls, ten official inline blocks, three library-origin blocks, zero returnable blocks; binary-only negative passes. |
| `node tools/kotlin-ets/tests/lowering/run.mjs` | `tests/lowering/.work/run-N22j1Z` | Six JVM/ETS values agree, including side-effectful source `toString` before and after mutation; official `String.plus` calls 25 to 0; 75 declarations and source names/file/offsets retained; production frontend defaults to the official pass. |
| `node tools/kotlin-ets/tests/language/typed.mjs` | `tests/language/.work/typed-0Jyasx` | Typed symbol identity, defaults, adapter precedence/result rejection, statement-only effects and Unit coercion pass; stored/returned external values still reject with valid source spans. |

The typed harness's explicit compile list now includes `LibraryInlining.kt` and
the language layer's `TypeSubstitution.kt` dependency. No negative assertion was
weakened or relocated. Shared `Contract.kt`/`Backend.kt` compiler opt-in warnings
remain warnings, not failed tests.

Earlier `tests/inline/.work/run-ncSDtA` passed the official inline and built-JAR
body probes but could not compile the public CLI (`hasQuestionMark` unresolved;
Validator missing its type-parameter branch). The typed attempts
`typed-zcJPg5` and `typed-wKsZDm` likewise stopped at compilation, before negative
assertions. These were integration blockers, not behavioral RED or GREEN.

The successful run's `binary-only.json` records the expected CLI exit 2:

```text
UNSUPPORTED: External inline call has no loaded IR body: inlinelibrary.libraryTransform.
Provide explicit dependency source; binary library IR body loading is not supported.
Unsupported external call: inlinelibrary.libraryTransform
source: tests/inline/BinaryOnly.kt, start=86, end=141
```

The actual diagnostic contains the absolute source path. The test also verifies
that `binary-only.ets` does not exist. This expected failure does not imply binary
body loading works. The callback probe independently confirms the JAR declaration
has inline metadata and a binary container source, but no IR body.

Production source SHA-256 at this regression completion:

```text
616675dc312a8c16da9bf33a004026f4797308e00a9bddce696e0b4149c42c0c  src/core/Frontend.kt
27f8b02c015855aaf5c2823fea74a9d004e642ad4d3500bba87f56782458d17b  src/core/OfficialLowerings.kt
4f335932667e7f9a0b128e379dcbd58a4b6ee2899e6948fd9c421e7d1ce89531  src/core/LibraryInlining.kt
```

This establishes bounded public CLI execution, same-input JVM differential and
actual official IR transformation. It does not establish Harmony SDK/device
validity; that verification belongs to the integration owner. No new language
capability or production change was needed to finish this regression round.

## Boundaries

No JS KLIB universe is grafted onto JVM FIR symbols. No general binary body
loader, dependency packaging/discovery, full Kotlin inline pipeline, coroutine
intrinsic replacement, reified runtime type support or page-specific lowering is
claimed. Non-local returns that still cross unsupported target expression
boundaries remain subject to language-layer rejection. Arbitrary compiler plugin
and platform-runtime behavior is not established by these bounded fixtures.

The official implementation sources are pinned to the compiler 2.1.20 source
archive described in `official-lowering.md`, specifically `ir/inline/FunctionInlining.kt`,
`ir/inline/CommonInlineCallableReferenceToLambdaPhase.kt`,
`backend/common/lower/ReturnableBlockTransformer.kt`,
`backend/jvm/JvmIrDeserializerImpl.kt`, and
`backend/common/serialization/NonLinkingIrInlineFunctionDeserializer.kt` under
`org/jetbrains/kotlin/` in that archive. The IR harness records the inliner class's
actual loaded compiler JAR. These are pinned compiler-internal APIs.
