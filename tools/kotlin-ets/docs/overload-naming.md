# Bounded Source Overloads

R2D language producer remains frozen. Main's final-revision focused and public
proofs passed; the two historical expectations are now explicit positives with
their original filenames/bytes. The migrated owning-suite runners await execution.
Full combined SDK/build/install/interaction/visual tests are deferred to R2/R3
architectural completion, final acceptance, or a genuine large cross-module
change. Deferred tests are not reported as passed; minimal targeted SDK remains
appropriate for new target syntax.

## Supported Slice

An overload group belongs to one source file or one final class without heritage.
Calls retain the exact Kotlin 2.1.20 resolved `IrSimpleFunction` declaration.
Top-level arity/type overloads, nonvirtual final-class overloads, and existing
generic class/member substitutions use the same declaration-bound naming plan.
`Int` and `Double` may both become target `number`; there is no runtime type test,
overload reselection, dispatcher, JavaScript ABI bridge, or output text rewrite.

`OverloadNaming` scans the actual module before constructing declarations/calls.
It reserves unchanged source bindings, including parameters and locals, then
orders declarations by source file path and original offsets. The first member
of each group keeps its spelling. Only the other N-1 bodies receive fresh names.
The official declaration-keyed `NameTable<IrSimpleFunction>` supplies collision
avoidance. Calls before declarations, recursion, and calls inside generic bodies
use this same plan, independent of call visitation order.

`EtsFunction.name` and `EtsSymbol.name` are emitted spellings. Only renamed
functions set `EtsFunction.sourceName`; `etsFunctionSymbol` derives canonical
identity from the original name and source span. References and members retain
that canonical ID and the instantiated function type. Target consumers do not
perform source overload resolution. Parameter/type-binder names remain unchanged.

Overloaded inherited/open/interface methods, extension/context receivers,
default/vararg parameters, suspend/reified functions, and callable references
remain outside this slice. Existing constructor/nested/variance boundaries are
not expanded. An overload group split across source files is not claimed.
Cross-file callers of a group declared in one file passed the bounded public proof.

## Official Reuse

Pinned source root: `/tmp/kotlin-official-lowering-readonly-EFO5dk/sources`.
Paths below are relative to that source root, Kotlin v2.1.20.

- Direct reuse: `org/jetbrains/kotlin/ir/backend/js/utils/NameTables.kt:36-75`,
  `NameTable`, `declareStableName`, and `declareFreshName`; `:266` sanitizes names.
- Reference: `org/jetbrains/kotlin/ir/backend/js/transformers/irToJs/JsNameLinkingNamer.kt:25-73`
  binds names to declarations rather than call-site strings.
- Reference: `org/jetbrains/kotlin/ir/backend/js/transformers/irToJs/jsAstUtils.kt:164-181`
  and `:240-248` use the resolved call owner and ordered receiver/arguments.
- Reference only: `org/jetbrains/kotlin/ir/backend/js/utils/NameTables.kt:120-189`
  computes JS member signatures using original types and fake overrides. Its JS
  ABI mangling is not installed in the ETS producer.
- Reference only: `org/jetbrains/kotlin/backend/common/serialization/mangle/ir/IrMangleComputer.kt:92-131`
  uses original classifier/type-parameter identities rather than collapsed target
  types; the bounded ETS implementation needs no additional signature mangler.

## Focused Evidence

Evidence directories are under `tests/language/overloads/.work/`:

- `baseline-PoW1VD/result.json`: original JVM oracle succeeds; preserved producer
  rejects actual overload IR with no ETS output. The baseline source snapshot is
  `/tmp/kotlin-ets-overloads-baseline-mLH0aj/src`, with `LanguageLowering.kt` SHA256
  `7bf06e6123cf4ebcc2136c5040dbd1cd53c90007c41430bce6486848acfbe9ef`.
- `probe-f9QqSO/result.json`: 30 same-input JVM/host outcomes; 30 declarations,
  9 minimal renamed bodies, and 29 actual source-call bindings. Seven valid Kotlin
  unsupported inputs reject with source spans/no output; two invalid declarations
  reject in original JVM and frontend. All 41 captured input hashes stayed fixed.
- `probe-f9QqSO/actual.ir` and `bindings.txt` retain official IR and canonical
  declaration/call evidence. Host execution uses SDK TypeScript transpilation,
  not an ArkTS SDK compilation claim.

Frozen SHA256 values:

| File | SHA256 |
| --- | --- |
| `src/language/LanguageLowering.kt` | `7bdaedf74617b92325664c569716c6e8318278f5d4ff29f482108df2f2930ad8` |
| `src/language/OverloadNaming.kt` | `47805bd604d599da3e404c1e9838633ea77256d74bf254812e45780b1630d3dc` |
| `tests/language/overloads/Overloads.kt` | `38a360d558c88784ada5bb22fa30dc688b267e395990b675ecefc2f302ef1efe` |
| `probe-f9QqSO/Overloads.ets` | `1148d4bb3945e5652455a92d41e59b64adf012bab4afe8fc1ab0dce00bd8bc2f` |

## Prepared Public Replay

Main completed `probe-gvr5mt/result.json` and `public-WddLTc/result.json` under
`tests/language/overloads/.work/` on final stdlib Rules SHA256
`5167d21ad317388e43f08739a7872cc89dda3150deaa7c18e5d974c4bc5b0889`.
The public proof passed all 45 same-input JVM/host pairs, including both original
legacy source hashes and five cross-file pairs. Complete public `Overloads.ets`
still matches focused SHA256 `1148d4bb3945e5652455a92d41e59b64adf012bab4afe8fc1ab0dce00bd8bc2f`.
The earlier focused/baseline manifests and replay runner remain untouched.

From `tools/kotlin-ets`, only after a new exclusive public compiler grant:

```sh
KOTLIN_ETS_BUILD_SLOT=1 node tests/language/overloads/public.mjs \
  tests/language/overloads/.work/probe-gvr5mt/result.json \
  tests/language/overloads/.work/baseline-PoW1VD/result.json
```

The runner pins the complete focused production file set and hashes, launcher,
compiler script, original fixtures, companions, and manifests before/after every
child. All JVM children use two active processors and SerialGC, serially. It uses
the executable public launcher with fresh `--out` / `--out-dir` destinations.
Logs, command statuses, original legacy bytes, output hashes, and comparisons are
retained in a fresh `.work/public-*` directory, including on failure.

The assertions are the exact focused ETS hash and 30 refreshed original
JVM/public-host pairs; five cross-file direct-call pairs; ten pairs from explicit
test consumers of the two unchanged historical fixtures. The companion consumers
are test sources, not fabricated bodies in the original fixtures. Generated ETS
bytes are never edited. This runner does not build SDK/native or migrate tests.

Historical inputs remain unchanged. Main accepted their exact positive public
evidence before authorizing the owning-runner migrations:

| Historical Input | Required SHA256 |
| --- | --- |
| `tests/language/UnsupportedOverload.kt` | `5e57cc93836b525a2db8eb6d90af5b387b9319d6894cedddcc1b06c0eb444cb0` |
| `tests/inheritance/methods/UnsupportedOverload.kt` | `78e12b4c6f3478ec5aefbbb66eb56666db90e30fb8c99fc0ea85773994de6028` |

## Mandatory Legacy Positives

`tests/language/run.mjs` keeps `UnsupportedOverload.kt` in its fixture list but
routes that exact filename to `tests/inheritance/methods/overload-positive.mjs top`.
`tests/inheritance/methods/probe.mjs` runs the same proof with `member` before
excluding its exact historical path from negative enumeration. A failed child
fails its parent suite; there is no unchecked skip. Baseline mode is unchanged.

The proof checks the pinned original bytes, compiles original Kotlin plus the
previously accepted explicit test consumers, invokes the public launcher into a
fresh directory, and compares five host outcomes to the original JVM oracle for
the selected fixture. It records hashes, commands, streams, original source
bytes, outputs, and comparisons in `tests/inheritance/methods/.work/overload-*`.
It does not depend on saved `.work` artifacts to succeed in future suite runs.

Ready affected-suite commands from `tools/kotlin-ets`, after a compiler grant:

```sh
JAVA_TOOL_OPTIONS='-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' \
  node tests/language/run.mjs UnsupportedOverload.kt
JAVA_TOOL_OPTIONS='-XX:ActiveProcessorCount=2 -XX:+UseSerialGC' \
  node tests/inheritance/methods/probe.mjs
```

The member positive can also be isolated with
`node tests/inheritance/methods/overload-positive.mjs member`; the normal methods
probe always performs it itself. Migration preparation validation is JavaScript
syntax only. No JVM, SDK, or native command was run during these test/docs edits.
