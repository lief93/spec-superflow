# Official Common Lowering

The production frontend now invokes Kotlin 2.1.20's
`org.jetbrains.kotlin.backend.common.lower.FlattenStringConcatenationLowering`
directly after successful JVM FIR2IR and before the target callback, while the
compiler project is alive. Both normal CLI modes use this frontend. There is no
opt-in flag, copied implementation, fake backend context, Kotlin source parser,
JavaScript intermediate, or JVM backend/codegen phase invocation.

## Reused Implementation

The pass is loaded from the installed `kotlin-compiler-embeddable-2.1.20.jar`.
Its [official source](https://github.com/JetBrains/kotlin/blob/v2.1.20/compiler/ir/backend.common/src/org/jetbrains/kotlin/backend/common/lower/FlattenStringConcatenationLowering.kt)
recognizes resolved String `plus` calls, flattens nested concatenations and folds
constant operands into Kotlin-formatted string constants. The pass takes a real
`CommonBackendContext`; this integration supplies the official `JvmBackendContext`,
not an implementation whose unused services throw or return invented symbols.

`src/core/OfficialLowerings.kt` follows the context construction in official
`JvmIrCodegenFactory.invokeLowerings` and the FIR state setup in
`KotlinToJVMBytecodeCompiler.runLowerings`:

- `GenerationState` uses the current project, configuration, module descriptor,
  diagnostics and `FirJvmBackendClassResolver(result.components)`.
- The context receives the same compilation's `irBuiltIns`, `symbolTable`,
  `components.irProviders`, FIR backend extension and plugin context, together
  with the official JVM generator extensions and IR deserializer.
- `ExternalDependenciesGenerator` resolves symbols referenced during context
  construction, as it does in the official JVM factory.
- Only `FlattenStringConcatenationLowering.lower(IrFile)` runs. No class bytecode
  is emitted; no default-argument, boxing, closure, inline or other JVM phases run.
- No serializer is needed because this path does not serialize JVM IR.
  The frontend's existing `finally` disposes the compiler project on success or
  failure after the target callback.

Lifecycle check: both the 2.1.20 source and installed-class `javap` show that
`GenerationState` has no `destroy`, `close`, `dispose`, or `AutoCloseable` contract.
`ClassBuilderFactory` also has no close method. `ClassFileFactory.done()` runs
code-generation finalizer extensions; it is not a resource destructor and is
intentionally not called here. `releaseGeneratedOutput()` only clears generated
output maps; this path emits none. No obsolete lifecycle method is invented.

Context construction is not claimed to be completely side-effect-free:
`JvmSymbols` creates external packages/symbols, the context initializes caches
and state callbacks, and dependency providers may materialize declarations.
Those are distinct from running JVM lowering passes on the source module.
The IR evidence test checks byte-identical source-module dumps and identical
declarations before/after the production context setup helper, same-compilation
builtins/symbol-table/provider identity, and empty bytecode output. This bounds
the claim to the exercised official frontend/fixture, not arbitrary third-party
compiler-plugin initialization or every possible serialized JVM dependency.

The compiler sources were read from the official Maven
[2.1.20 source archive](https://repo.maven.apache.org/maven2/org/jetbrains/kotlin/kotlin-compiler-embeddable/2.1.20/kotlin-compiler-embeddable-2.1.20-sources.jar),
cached at `/tmp/kotlin-official-lowering-readonly-EFO5dk/`.
Archive SHA-256: `dc1ec1391e465b56d7e664fcf63d0ff4cfeb7274fc6e2b0dbd71335f8ce1dc11`.
Installed compiler JAR SHA-256:
`c54a00718c8c0e3ee858bf42771c7f401c5e3c1738861e18e9536371042fa1b3`.
These are compiler-internal APIs pinned to 2.1.20, not a stable public plugin API.

## Reproduction And Evidence

Run from the repository root:

```sh
node tools/kotlin-ets/tests/lowering/run.mjs
```

The runner retains every subprocess command/status/stdout/stderr under a fresh
`tests/lowering/.work/run-*` directory. It compiles the same `Concatenation.kt`
with the official JVM compiler plus a test-only driver, checks six independent
literal expected results, runs the normal source-to-ETS CLI, and executes the
generated module through the installed DevEco TypeScript runtime. Results must
match for changed inputs, nullable prefixes, nested concatenation, constant
decimal formatting, mutation order and renamed source functions/parameters.

The custom `MutableText.toString()` reads its counter, increments it and appends
a `T<old-count>` event. The same concatenation then calls `mutate()` (adds ten and
records `M<old-count>`) and stringifies the object again. For initial counters 2
and -3, JVM and ETS must respectively produce event orders `T2>M3>T13>` and
`T-3>M-2>T8>`, final counts 14 and 9, and strings containing both old and new
states. These assertions detect delayed, reordered or repeated string conversion;
they do not merely test the order of string-returning arguments.

`IrEvidence.kt` separately uses the real official frontend to inspect the same
module immediately before and after the production lowering function. It asserts
non-zero input String-plus calls and zero afterward, identical source declaration
objects/names/offsets, unchanged file-entry identity/path, preserved effectful
call objects and valid offsets, and retained outer expression spans. It saves
`before.ir` and `after.ir`, reports the official pass's loaded JAR and compiler
version, and checks that `withKotlinModule` applies the stage by default.

Behavioral RED: `.work/run-A0QvtM` had successful JVM compilation/runtime, but the
normal CLI rejected `kotlin.plus` at source offsets 375..403 with exit 2.
Initial GREEN: `.work/run-HWmgFr` passed the CLI/JVM comparison and actual IR
checks: 14 String-plus calls became zero; 42 declaration records and four
effectful `record` call identities were preserved. This is a transformation
assertion, not a target text snapshot or synthetic IR test.

Final GREEN: `.work/run-puu4KR` additionally records the loaded official compiler
JAR/version and passes the isolated context-construction checks (unchanged source
IR, original compilation services, empty bytecode output). The existing twelve
language CLI fixtures also passed in `tests/language/.work/run-7USatH` with the
official stage enabled; their files and oracles were not modified by this batch.

The side-effectful `toString` extension passed `.work/run-WHHFKk`: all six literal
and same-input JVM/ETS results match, context setup leaves source IR unchanged,
and 25 String-plus calls become zero with 75 source declaration records preserved.
`runtime.json` retains the exact expected/actual state and event strings. Only
the lowering tests and this document changed for this extension; production
`Frontend.kt` and `OfficialLowerings.kt` retained their accepted hashes.

## Boundaries

This is one common IR normalization stage, not full Kotlin/JS lowering reuse.
It does not load ordinary JVM library bytecode as IR bodies, link JS KLIBs, inline
library functions, or supply JS runtime semantics. Constant decimal conversion
performed by the official pass does not establish support for runtime
Float/Double formatting, arbitrary collection/object coercion or the broader
stdlib. Existing target diagnostics remain responsible for unsupported operands.

The production pass can fold away an expression and merge constant source spans;
the guarantees tested here concern surviving declarations/effectful calls and
outer transformed spans, not one-to-one preservation of every original IR node.
No SDK, device or page-suite verification is claimed for this batch. Independent
review and commit/push are not performed.

Test harnesses that compile `Frontend.kt` through an explicit source list must
also include `OfficialLowerings.kt`; the public launcher already discovers all
core sources. The integration owner updated `tests/language/typed.mjs` accordingly.
Subsequent SDK compilation and combined-module evidence are recorded in
[Parallel Backend Batch](parallel-backend-batch.md).
