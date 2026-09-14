# R2A Generic Binary Inline Bodies

Status: production implemented and frozen; focused real-IR/JVM checks and the
main task's full-revision public CLI/JVM/host replay are GREEN. SDK/native
verification remains pending with the main task. This is a bounded R2A increment,
not completion of R2 or general JVM interoperability.

## Scope

Real Kotlin 2.1.20 `-Xserialize-ir=inline` top-level JVM file-facade bodies with
non-reified type parameters, one transitive generic helper, Int and source-owned
object call-site instantiations. The consumer receives JARs, never producer source.
Entry and helper use different type parameter names. Existing reified, member,
multifile, signature-only and missing-transitive-body boundaries remain closed.

## Official Machinery

Pinned upstream: Maven `org.jetbrains.kotlin:kotlin-compiler-embeddable:2.1.20`,
sources archive SHA-256
`dc1ec1391e465b56d7e664fcf63d0ff4cfeb7274fc6e2b0dbd71335f8ce1dc11`.
Local cache: `/tmp/kotlin-official-lowering-readonly-EFO5dk/sources`.
Paths below are beneath `org/jetbrains/kotlin/` in that archive.

| Official Source | Reused Boundary |
| --- | --- |
| `backend/jvm/JvmIrDeserializerImpl.kt` | Real serialized class metadata, current frontend builtins/symbol table/providers. |
| `backend/jvm/serialization/deserializeLazyDeclarations.kt` | Official `IrDeclarationDeserializer` with `allowAlreadyBoundSymbols=true`; public references go through the supplied symbol table. |
| `backend/common/serialization/IrDeclarationDeserializer.kt` | `deserializeIrTypeParameter` reuses bound public type parameter symbols; decodes bounds and signatures from actual bytes. |
| `backend/common/serialization/signature/IdSignatureComputers.kt` | `PublicIdSignatureComputer.visitTypeParameter` identifies parameters by parent signature plus index, not spelling. |
| `ir/util/SymbolTable.kt` | `declareGlobalTypeParameter` and `referenceTypeParameter` preserve canonical public classifier identity. |
| `ir/inline/FunctionInlining.kt` | Associates actual call-site type arguments with callee `IrTypeParameterSymbol`s and runs the common inliner. |
| `ir/inline/InlineFunctionBodyPreprocessor.kt` | Official symbol deep-copy/type remapper handles non-reified erasure, substitution, nullability and copied classifier references. No parallel substitution algorithm is introduced. |
| `ir/backend/js/lower/inline/JsInlineFunctionResolver.kt` | JS uses the common inline resolver machinery but adds JS coroutine/runtime context. That backend-specific resolver is not transplanted into the JVM frontend. |

## Reproducible Commands

Run only when the main task grants the appropriate compiler slot:

```sh
node tests/binary-bodies/r2/run.mjs --red
node tests/binary-bodies/r2/run.mjs
# All shared production writers must be frozen for this command:
node tests/binary-bodies/r2/replay.mjs tests/binary-bodies/r2/.work/run-gzlJUt
```

The harness pins `JAVA_TOOL_OPTIONS=-XX:ActiveProcessorCount=2 -XX:+UseSerialGC`.
Focused evidence checks actual official inline blocks, original body/declaration
identity, linked generic signature classifiers and absence of residual generic
classifiers in the concrete consumer IR. Binary provenance uses the actual class
`SourceFile` attribute, serialized body offsets and explicitly unknown line data;
it is not a claim that original producer source exists locally.

Public replay records exact production/input SHA-256s and compares Int overflow,
argument/closure effects and shared object mutation against the same-input JVM.
Node/DevEco TypeScript execution is not Harmony SDK acceptance. SDK integration
is owned by the main task, not this lane.

## Implementation And Evidence

Only `src/core/BinaryBodies.kt` changed in production. It registers original FIR
type parameters using official public signatures before deserialization, seeds
upper-bound classifiers, and verifies that decoding retains the exact parameter
owners, upper bounds and parameter/return classifier identities. No type-name
substitution or parallel body-copy algorithm was added. `LibraryInlining.kt`
continues to invoke the actual common inliner unchanged.

Real IR contains the common inliner's non-reified erasure to `kotlin.Any` and
`IMPLICIT_CAST` back to Int or source Box at usage boundaries. It contains ordinary
blocks/temporaries and official inline blocks, not new target nodes. Concrete
consumer expressions have no residual type-parameter classifiers.

Evidence directories are relative to `tests/binary-bodies/r2/.work/`:

| Run | Result |
| --- | --- |
| `run-5XfxtL` | Genuine RED: official producer and three JVM oracle cases passed; production frontend rejected generic serialized `direct` with the previous non-generic guard. `combined-evidence.json` preserves the failure. |
| `run-W10X4e` | First GREEN: same-JAR cross-facade and second-JAR dependency graphs each produced five checked generic inline blocks. |
| `run-gzlJUt` | Final focused GREEN: both layouts, original body/symbol/type linkage, parameter names, binary provenance and seven boundary cases passed. `identity.json`, `producers.json`, `production.ir`, `bodies.txt` and command JSON records retain exact evidence. |
| `run-gzlJUt/public-m9ONEk` | Main-owned full-revision public replay GREEN: both layouts, six same-input JVM/target pairs and seven closed failures passed. `complete.json` confirms `implementationUnchanged=true`; `identity.json`, `runtime.json` and per-command JSON retain the tested revision and results. |

Both public outputs (`combined.ets` and `second-jar.ets`) have SHA-256
`5d0822e71b7a1b8811d57dc98374f202cbad9483718efcdc10780b62a0973620`.
This replay used the existing real producer JARs through the normal public CLI;
target execution used Node with the installed DevEco TypeScript runtime. No
SDK/native result is claimed from this host replay.

The actual decoded metadata contains 764 bytes for Direct.kt, 790 for Entry.kt,
and 763 for Helper.kt; each serialized-payload SHA-256 is recorded in `bodies.txt`.
The consumer receives only its own Application.kt and producer JARs. The helper
is not imported by the consumer and has differently named type parameters.

Boundary results: ordinary JAR signatures remain `FunctionBody.Unavailable`
without any manufactured body. Missing transitive serialized bytes, missing
helper JAR, stripped real SourceFile, reified inline, member inline and multifile
parts reject with consumer file and nonnegative call offsets. A binary SourceFile
record never becomes a pretend local source file or known line map.

Frozen production SHA-256:

```text
c397bd481d816e4c8882682e163f891289df4647020e84f0d039df74cca2782b  src/core/BinaryBodies.kt
7bb29b03e1f29047451060cd322011907a6171c37f5e7c30f51c4daeadcc9fc0  src/core/LibraryInlining.kt (unchanged)
```

## Remaining Boundaries

This increment exercises two non-reified `Any`-bounded type parameters, Int and
source-owned Box instantiations, one transitive generic helper, closure effects
and shared object mutation. It does not claim arbitrary bounds/variance, generic
default arguments, reified bodies, class/member binary loading, constructors,
multifile/KLIB formats, or binary compatibility beyond pinned Kotlin 2.1.20.
Existing reachable-body operation/linkage guards and cycle rejection remain.
Host differential is now independently verified by the public replay above.
SDK/native acceptance remains pending with the main task and is not inferred
from either focused IR success or Node/TypeScript execution.
