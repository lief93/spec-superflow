# R1 serialized inline reachability

## Implementation

R1 extends `BinaryBodies.kt`; no Frontend, shared contract, target, language or
stdlib changes are required. `LibraryInlining.kt` continues using the existing
`FunctionBodies` resolver and official common inliner unchanged.

The loader now binds real declarations that application IR never referenced:

1. Decode the actual JVM serialized signature table using official
   `JvmIr.ClassOrFile`, `IrLibraryFile` and `IdSignatureDeserializer`.
2. Use the signature's structured package/callable name only to enumerate
   candidates from the actual FIR session's `symbolProvider`. Obtain their
   existing IR declarations through `Fir2IrDeclarationStorage.getIrFunctionSymbol`.
3. Select by equality with the entire official `PublicIdSignatureComputer`
   (`JvmIrMangler`) result, including overload identity. Never select the first
   same-name declaration or synthesize a body/signature stub.
4. Register those actual declarations and canonical signature types before
   `JvmIrDeserializerImpl`, so loaded helper bodies keep real symbol identities
   and parents. Only inline owners receive binary provenance parents; ordinary
   external function stubs remain external.
5. Traverse actual deserialized body/default-argument call references. Recursively
   load each reachable inline dependency from its resolved binary owner, validate
   types/references/provenance and detect DFS back edges before official inlining.
   Publish `Available` only after the reachable dependency checks succeed.

The whole facade is still deserialized by the official implementation. The
availability graph, however, no longer rejects a root merely because an unrelated
serialized sibling contains an unsupported call. The fixture includes an unused
inline sibling calling a non-inline function and an unused same-name String
overload; only the Int helper is inlined into the consumer.

## Provenance and diagnostics

The prior real class `SourceFile` route is retained. Each helper has its own
actual JAR/class location plus `#SourceFile=...`, body offsets from serialized IR,
unknown debug lines/columns, and the original linked declaration/body identity.
No original source file is assumed present and no source-by-name lookup is used.

Failures distinguish an absent helper artifact, a resolved helper with no
serialized body, absent helper SourceFile metadata, a non-inline body dependency,
and a reachable cycle. The primary diagnostic retains the consumer call span;
body/provenance failures name the actual dependency artifact or full signature.
The R1 fixture consumer span is `131..231`.

The previous binary baseline's `hiddenOffset` is now resolved through FIR, so its
negative correctly changes from *unlinked symbol* to *unsupported non-inline
serialized body call*. Its body still is not fabricated or considered available.

## Finite cases

| Case | Producer/input | Required observation |
| --- | --- | --- |
| Same file | `Same.kt`, genuine serialized JAR | Entry and helper both appear as official inlined blocks |
| Cross facade | `Entry.kt` + `Helper.kt`, one real JAR | Two distinct binary SourceFile identities |
| Second JAR | Helper JAR, then entry compiled against it | Consumer references only entry; actual helper body comes from second JAR |
| Missing body | Replace helper with ordinary signature-only JAR | Named dependency body unavailable, not a bytecode substitute |
| Missing artifact | Consumer classpath has entry JAR only | Exact unresolved serialized helper signature |
| Missing provenance | Remove SourceFile only from genuine helper JAR | Reject before emission, no guessed filename |
| Cycle | Independently compiled bootstrap/updated versions | Reject `entry -> helper -> entry` before common inliner |

The cycle producer is not fabricated IR: compile a bootstrap entry, compile helper
against it, then compile the final entry against that helper. Consumer classpath
contains only the final entry and helper. Their real serialized IR references
form a cycle even though the separately compiled bytecode had already inlined the
bootstrap implementation. No class body rewriting is used for this case.

Each positive uses observable callback mutations and argument values. JVM inputs
are `1`, `-2`, and `Int.MAX_VALUE`, including overflow of the helper's next value.
Expected results: `27/2/:1:2`, `-15/2/:-2:-1`,
`-1/2/:2147483647:-2147483648`.

## Commands and evidence

From `tools/kotlin-ets`, run the focused lane checks serially:

```sh
node tests/binary-bodies/r1/run.mjs
node tests/binary-bodies/run.mjs --evidence-only
```

All JVM processes use `-XX:ActiveProcessorCount=2 -XX:+UseSerialGC`.
Focused checks do not build the public CLI or claim target runtime/SDK success.

RED: `tests/binary-bodies/.work/r1-Un6iHB/same-evidence.json`, exit 1. The real
producer and JVM oracle succeeded; current production failed because the loaded
helper declaration's parent was uninitialized. This was not a missing CLI test.

Initial focused GREEN: `r1-xL8VFL`, all three positives and four negatives, exit 0.
Final focused GREEN: `r1-nV4Gu7`, same cases, exit 0. Existing binary baseline
`node tests/binary-bodies/run.mjs --evidence-only` also passes in `policy-WdK3h6`.
No full CLI build was run during the parallel writer interval.

Frozen production SHA-256:

- `BinaryBodies.kt`: `34a34162a2d08bd84ed073ce2046972d081df9d29fdb68aea9737ad450793b65`
- `LibraryInlining.kt` (unchanged): `7bb29b03e1f29047451060cd322011907a6171c37f5e7c30f51c4daeadcc9fc0`

Only when main grants the full build slot, reuse completed producers:

```sh
node tests/binary-bodies/r1/replay.mjs tests/binary-bodies/.work/r1-nV4Gu7
```

Replay makes no dependency JARs. For each positive it independently builds/runs
the same consumer against that producer, invokes the real public CLI, executes
generated ETS with DevEco TypeScript/Node and compares all three inputs. Four
negative public CLI cases require source-linked failure and no output. The
manifest records exact inputs/current implementation hashes and verifies that
production stays unchanged throughout. Main owns subsequent SDK/native evidence.

After main froze all production writers and granted the first exclusive build
slot, that exact replay command passed with exit 0 in
`tests/binary-bodies/.work/r1-nV4Gu7/public-NxdHXC/`. `complete.json` records three
positive layouts, nine JVM/target pairs, four source-linked negative cases with
no target, and `implementationUnchanged=true`. `identity.json` and the individual
command JSON files retain the exact implementation, inputs and commands.

`same.ets`, `cross-facade.ets` and `second-jar.ets` all have SHA-256
`2ca5024184261084280a3e28967122a9bf62707ebf995f3110d0765d588c9aff`.
The slot was released after the process completed; no process was left running.
This proves public CLI plus host execution, not an SDK or native result. Main
has these exact generated files for subsequent integration.

## Changed files

- Production: `src/core/BinaryBodies.kt` only. `LibraryInlining.kt`, Frontend and
  all shared/other-lane sources were unchanged by this lane in R1.
- Existing test: `tests/binary-bodies/run.mjs` updates the resolved non-inline
  helper diagnostic expectation, without weakening the failure/no-output checks.
- New `tests/binary-bodies/r1/`: `Same.kt`, `Entry.kt`, `Helper.kt`, `Bootstrap.kt`,
  `CycleHelper.kt`, `Application.kt`, `Oracle.kt`, `Evidence.kt`, `run.mjs`,
  `replay.mjs`.
- Documentation: this file and the R1 pointer in `docs/binary-bodies.md`.

## Upstream reuse and limits

Pinned compiler/source checksums are in [binary-bodies.md](binary-bodies.md).
Additional official sources under `org/jetbrains/kotlin/`:

- `backend/common/serialization/IdSignatureDeserializer.kt`: actual signature decoding.
- `backend/common/serialization/IrFileDeserializer.kt`: public `IrLibraryFile` view of real tables.
- `fir/resolve/providers/FirSymbolProvider.kt`: official dependency candidate lookup.
- `fir/backend/Fir2IrDeclarationStorage.kt`: actual cached FIR-to-IR symbol retrieval.

This remains non-generic top-level JVM file-facade inline support. Member/generic
inline, KLIB/other producer formats, constructors and arbitrary non-inline binary
APIs are not added. Every reachable non-canonical dependency must have a supported
serialized inline body; this is not a generic adapter fallback or bytecode linker.
Malformed class-level metadata can still prevent facade deserialization even
when a particular malformed sibling is unreachable. Existing language/type
capability limits still apply after the official phases.
