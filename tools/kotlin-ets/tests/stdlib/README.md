# Standard library slice

Integration API (package `dev.ets`):

```kotlin
class StandardLibraryRules : CallRule {
    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression?
    fun supportLines(): List<String>
}
```

The zero-argument rule must be installed in the language lowering's rules. In
language mode, emit `standardLibrarySupportLines(program)` once before printing
the typed program. Page mode retains `rules.supportLines()` until its text emitter
exposes complete typed dependencies. See [runtime dependencies](../../docs/runtime-dependencies.md).
Seven
small functions preserve integer division/remainder, list bounds/append/map, and
substring bounds. The emitted expressions call `__etsIntDiv`, `__etsIntRem`,
`__etsListGet`, `__etsListAdd`, `__etsListMap`, `__etsSubstring`, and
`__etsSubstringFrom`; omitting the support lines leaves unbound calls. Reserve
these generated names in the integration owner if source-name collisions are
supported. The rule object holds no per-module state.

`listOf`/`mutableListOf` return typed `Array<T>` literals. `get` and `add` use
generic helper calls. `map` delegates its actual function expression to
`Language.expression`, and the helper passes one argument in index order.
Statements, lexical binding, lambda returns, and `IrStringConcatenation` belong
to the language lowering. All input-dependent stdlib output uses the shared
typed target nodes; no expression source text is constructed or replaced.
`Language.source(call)` supplies the original file and offsets. External helper
symbols and member callees have precise instantiated `EtsFunctionType` values,
and generic helper calls carry typed arguments. The unchanged static runtime
bodies live in `src/stdlib/StandardLibrarySupport.kt`; only selected declarations
and their real transitive dependencies are emitted in language mode.

## Bounded behavior

Exact pre-backend Kotlin 2.1.20 symbols and actual receiver/argument/result types
select the rules. No source parsing or fixture-dependent production behavior.
The supported set covers Int arithmetic/comparison/unary operations, eager
Boolean operations, non-null scalar equality and `toString`, String concatenation,
UTF-16 length, substring, case-sensitive String contains/startsWith/endsWith,
list factories, List/MutableList get/size, one-argument add, and list map.
Int results wrap to signed 32 bits; division truncates toward zero and zero
divisors throw. List/map support is for the array-backed representation generated
by this slice. Adding to a list during map throws instead of silently using the
target Array.map iteration behavior.

Unknown symbols and unsupported overloads return null without lowering children.
Nullable scalar APIs, Long/Double arithmetic, Char operations, ignoreCase=true or
dynamic ignoreCase, general Iterable/Sequence operations, spreads, indexed add,
and structural list equality remain unsupported. Empty/default varargs are
handled only for the exact factory API; no invented arguments. `repeat` and
range iteration remain language/UI coordination work when requested.

## Reproduction

From the repository root:

```sh
bash tools/kotlin-ets/tests/stdlib/check-symbols.sh
bash tools/kotlin-ets/tests/stdlib/check-public-cli.sh
```

`check-symbols.sh` compiles this implementation and the shared contract with the
locally cached official Kotlin 2.1.20 compiler, runs K2/FIR2IR on real source files,
and checks acceptance/rejection on actual IrCall objects. Its recording Language
is only a seam for rule selection; this check does not prove target execution.
Each accepted expression is checked with the shared `EtsValidator`, including
bound operand symbols, call signatures, and result types. The harness also
temporarily substitutes malformed result types on real compiler calls, restores
the IR afterward, and verifies rejection before child lowering. Separate negative
tests corrupt emitted target-call result types and require `InvalidTarget`.

Typed migration verification: 71 positive calls accepted, six unsupported APIs
rejected (plus the negative fixture's one supported Int.plus). All 79 malformed
IR result variants and 27 malformed target-call results were rejected. The
focused compiler run used `JAVA_TOOL_OPTIONS=-Xmx512m`. The static runtime literal
was verified unchanged from the pre-migration implementation. Prior runtime/SDK
evidence below applies to the earlier emitter; the typed architecture still needs
its integrated runtime and SDK reruns after capture permits those builds.

`check-public-cli.sh` compiles the source fixtures on Kotlin/JVM to produce a
runtime JSONL oracle, invokes the public source-to-ETS launcher on the same source
fixtures, and runs the generated artifact against that oracle. Each run uses a
fresh ignored `.build/cli.*` directory containing CLI stdout/stderr, the ETS
artifact (only on successful emission), and the JVM oracle. Test-only TypeScript
erasure uses the installed DevEco SDK compiler; override its module path with
`KOTLIN_ETS_TYPESCRIPT`. JSONL carries expected runtime values, never production
compiler input. This proves host execution only; ArkTS SDK compilation and
device checks are owned by integration/verification workers.

Initial public-CLI attempt `.build/cli.1XNKNO` failed closed with exit 2,
`Language function emission is not implemented`, at Lists.kt offsets 21..62.
No output artifact was created. Re-run after language integration and helper
plumbing are available; the initial result is not an end-to-end pass.

Second attempt `.build/cli.D2yJxr` emitted the complete source fixture set and
produced 66 independent JVM oracle cases. Target runtime failed immediately with
`ReferenceError: __etsIntDiv is not defined`: Main.kt had not yet emitted the
support lines. Array casts, generic calls, local list mutation, and map lambda
statements were emitted through the public CLI without contract changes.
The latest real-IR checks passed 71 supported calls and all six unsupported APIs
(the negative fixture also contains one supported Int.plus inside Sequence.map).
The public CLI separately rejected UnknownApi.kt with exit 2 and
`Unsupported external call: kotlin.text.lowercase`, source offsets 71..82, and
no target file. At that initial checkpoint, this worker had not run an ArkTS
build or any device operation.

## Actual Harmony SDK compilation

```sh
node tools/kotlin-ets/tests/stdlib/check-sdk.mjs
```

The optional positional argument selects another read-only Harmony seed. The
default is `/private/tmp/kotlin-ets-native-20260913-07/harmony`. The test clones
that seed into a fresh `/tmp/kotlin-ets-stdlib-sdk-*` host, excluding previous
build output and Hvigor caches. It preserves the seed's installed dependencies
with relative symlinks, so no dependency installation is needed.

The public CLI independently generates Scalars.ets and Lists.ets from the two
positive Kotlin fixtures. The test copies those generated bytes verbatim and
forces both module imports from `sdk/Index.ets`. Actual DevEco Hvigor runs
`assembleHap --mode module -p module=entry@default -p product=default --no-daemon`.
Success requires both modules in the SDK's ETS compilation input manifest,
nonempty per-module protoBin files, Ark bytecode, and a HAP. Hash checks verify
that source fixtures, generated originals/staged copies, and the read-only seed
inputs did not change. `result.json` is marked successful only after those checks.

Each run retains command arguments/environment overrides, CLI output and errors,
SDK stdout/stderr, hashes, compiler outputs, and HAPs. The first SDK run at
`/tmp/kotlin-ets-stdlib-sdk-0bxfUt` passed CompileArkTS and HAP assembly. Both
positive generated modules were in filesInfo.txt as ETS and produced protoBin
files. Warnings were confined to the seed EntryAbility's exception handling;
there were no generated-stdlib diagnostics. Production stdlib code required no
changes. This is SDK compilation evidence; no device operations were performed.

The final harness rerun `/tmp/kotlin-ets-stdlib-sdk-dx12hE` also passed, including
automated compiler-input/protoBin/bytecode/HAP and integrity assertions.
`result.json` records each artifact hash; `integrity.json` confirms unchanged
seed inputs and generated bytes. Signed HAP SHA-256:
`88f4d68b364f337d18f7c5f1a26503fa21828d38a5d477acf4f56d204b2914aa`.
No LanguageEmitter issue was found in these positive stdlib fixtures.
