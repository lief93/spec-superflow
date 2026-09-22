# S1: serialized KLIB dependency capabilities

The follow-on [S1.4 collection architecture audit](klib-collection-architecture.md)
moves `filter` and `filterNot` through these official bodies and a canonical
symbol-bound collection runtime seam. The same seam now carries `map` and
`mapNotNull` plus indexed variants, including their official `*To`, traversal
and `let` closure. Non-indexed `flatMap` and `flatMapTo` reuse their official
bodies through the exact linked iterable `addAll` primitive; indexed flat-map
variants remain outside the admitted closure.

Scope: loading/linking reusable Kotlin bodies and selecting existing minimal ETS
runtime support. No Compose control, UI backend, public CLI, JVM bytecode
translation, JS backend phase pipeline or complete stdlib replacement is added.

## Audit and implementation

| Boundary | Existing behavior | S1 change |
| --- | --- | --- |
| JVM serialized IR | `BinaryBodies` deserializes checked inline JVM bodies; `LibraryInlining` runs the official common inliner | Keep format and admission policy; share only the official inliner invocation with the KLIB path |
| Serialized KLIB | `KlibLoader` uses official `ModulesStructure`, `loadIr`, `JsIrLinker`; explicit translated vs dependency-only libraries | Preserve official descriptor/symbol identities and attach canonical library paths to loaded module identities |
| Body availability | KLIB proofs inspected raw IR; shared body origins described source/JVM only | `KlibSession.bodies()` implements `FunctionBodies`, reports `SerializedKlibIr`, enforces borrowed lifetime, and admits dependency-only inline bodies only by explicit canonical symbol approval |
| Target compilation | Experiments directly invoked the backend | `KlibSession.lowerToEts()` shares the common inliner, then existing typed ETS lowering; records successful replacements and rejects unresolved dependency boundaries before target output |
| Runtime | `StandardLibraryDependencies` collects from typed ETS and existing support emission expands dependencies | Expose the collector's direct roots for evidence; keep a single collector and the existing per-module runtime closure |

Function FQNames/signatures in reports are display evidence. Production approval
and body ownership use canonical `IrFunctionSymbol` and module descriptor
identities, never a spelling-based list of stdlib APIs. KLIB is never sent through
`JvmIrDeserializerImpl` or treated as a JVM FIR session.

A translated library's non-inline bodies remain in their original files and are
emitted with existing symbol-based imports. Explicitly approved dependency-only
inline bodies are copied into callers by the official Kotlin common inliner;
the dependency's module is not emitted. A body being present is not permission
to compile an entire dependency or interpret JS-specific implementations as ETS.

The KLIB compiler context is the pinned official `JsIrBackendContext`, consistent
with its `JsIrLinker` symbol universe. This context resolves compiler symbols;
only shared callable-reference/inlining and returnable-block passes are invoked.
No `JsLoweringPhases`, JS text intermediate, JS runtime module or coroutine
runtime is emitted. This is distinct from promising the compiler never inspects
JS-platform declarations while constructing its official context.

## Three evidence classes

- `REUSABLE_BODY`: real deserialized body, canonical KLIB path, signature and
  producer file/offsets. The positive fixture links `dependencies.adjusted` from
  a separately serialized library and inlines official `kotlin.let` from the
  pinned Kotlin 2.1.20 stdlib. It also exercises a generic higher-order inline
  dependency (`twice`), without a per-function target rule.
- `TARGET_REPLACEMENT`: an existing `CallRule` actually returned a typed target
  result, with callee identity and caller source span. Int remainder uses the
  existing `__etsIntRem` boundary; the final typed ETS collector requests only
  that runtime root. This is not mislabeled as a loaded Kotlin implementation.
- `REJECTED`: a residual dependency-only call or external declaration for which
  no target rule supplies a result raises `UNSUPPORTED_KLIB_DEPENDENCY`. Its
  diagnostic carries caller source, canonical library path, callee signature
  and producer declaration span. No ETS output is written by the harness.

Producer sources are deleted after official KLIB compilation. Source offsets
remain deserialized provenance; they are not fabricated local source files.
Missing transitive KLIBs still fail through official linker diagnostics, with
partial linkage disabled, as verified by the existing loader regression.

## Reproduce

From `tools/kotlin-ets`, with `KOTLIN_JS_STDLIB` pointing to the pinned
`kotlin-stdlib-js-2.1.20.klib`:

```sh
node tests/klib/capabilities/run.mjs
node tests/klib/run.mjs
node tests/klib/portable-common/run.mjs
node tests/binary-bodies/r2e/run.mjs
node tests/binary-bodies/r2e/replay.mjs tests/binary-bodies/r2e/.work/<completed-run>
```

Each harness records commands, original/compiled input hashes, diagnostics and
results under its `.work/run-*` directory. `capabilities` strict-typechecks the
emitted modules with the installed DevEco TypeScript host and compares execution
to the JVM for positive, negative and overflowing Int inputs. It verifies real
cross-module imports, original body ownership, official inline consumption,
minimal runtime roots, no unrelated collection helpers, rejected output absence
and provider lifetime after session close. These are host semantic tests, not
ArkVM/device evidence.

## Boundaries

The three-way classification does not promise general Kotlin dependency support.
Unapproved dependency-only bodies are not silently copied; platform/external
calls need an existing typed replacement or fail. Approved inline bodies can
still expose unsupported residual operations, which must fail target lowering.
Full JS collections and coroutine implementations remain outside the admitted
runtime. This increment does not delete existing stdlib adapters or claim that
portable common source equivalents are identical to official JS collection
representations. In particular, `ArrayList` construction may reach `kotlin.js.js`.

## Frozen validation evidence

[Checked-in evidence](klib-dependency-capabilities-evidence.json) records the
pinned compiler/stdlib hashes, body and replacement provenance, typed runtime
selection, JVM/ETS results, rejection diagnostics and production source hashes.

1. **Source/selection:** `capabilities/.work/run-XX3AHU` records official
   `kotlin.let` from `src/kotlin/util/Standard.kt`, the selected dependency body,
   and the actual Int remainder replacement. Without explicit approval the
   dependency-only inline body remains unavailable. Emitted support is exactly
   `__etsIntRem` plus its `__etsThrowable` dependency, with none in Library.ets.
2. **Positive link/typed output:** that run preserves Library/Consumer imports,
   strict host typing and four JVM/ETS outcomes (`2`, `0`, `0`, `-1`), after
   deleting producer sources.
3. **Explicit rejection:** external no-body and non-selected non-inline body
   cases report library, declaration and call-site spans, with no ETS output.
4. **Regressions:** loader `run-vEVvEa` passes four host/JVM outcomes and missing
   transitive dependency rejection; portable-common `run-6oCL0H` passes 36 value
   cases, nine exhaustion cases and callback exception identity; current JVM
   member-inline `run-PWQ1Zr` passes 26 official inline blocks and seven refusal
   boundaries, and `replay-dbkLpR` passes three JVM/typed-ETS host pairs plus
   unmapped-type and invalid-bound rejection.
5. **Scope:** only this branch's dependency/inliner/runtime-selection code,
   focused tests and documentation are changed. No production UI files changed.

The first attempt to run the historical standalone R2 script stopped at its
outdated hand-maintained compile list (`SourceSelection` and `etsAssignable`
were already referenced by the baseline). The shared focused-test list was
refreshed with SourceSelection/SourceDiagnostics, and the current R2E suite
(which already compiles all target validation sources) is the green JVM gate.
This does not claim that the historical R2 runner itself was repaired.
