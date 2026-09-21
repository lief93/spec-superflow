# Dependency IR contract proposal

Status: proposal only. `src/core/Contract.kt` and `src/core/Frontend.kt` stay frozen.
This does not add a public KLIB CLI, JS lowering pipeline, or JVM signature reader
for KLIB files.

## Current contract

`FunctionBodies.resolve(IrFunctionSymbol)` already distinguishes:

| Result | Meaning |
| --- | --- |
| `Available` / `Origin.Source` | Body lives on a declaration in the current frontend source module |
| `Available` / `Origin.SerializedJvmIr(binaryLocation)` | Checked serialized JVM IR body from a class file |
| `Unavailable` | Unbound, external, no body, non-inline binary, missing metadata, or missing serialized IR |

A successful `CallResult` is a target replacement. It is not a Kotlin body and must
not change `FunctionBodies` availability.

`sourceFile(declaration)` currently treats `KotlinJvmBinarySourceElement` and
`JvmPackagePartSource` as non-source. KLIB files are `IrFile`s produced by official
deserialization; they are not JVM class provenance. Do not reuse the JVM binary
predicate for KLIB modules.

## Proposed addition (shared-contract owner)

```kotlin
sealed interface FunctionBody.Origin {
    data object Source : Origin
    data class SerializedJvmIr(val binaryLocation: String) : Origin
    data class SerializedKlibIr(
        val libraryLocation: String,
        val moduleName: String,
        val fileName: String,
    ) : Origin
}

enum class Reason {
    // existing JVM reasons...
    NON_TRANSLATED_KLIB,          // resolved, but the module is dependency-only
    KLIB_MISSING_BODY,            // deserialized declaration has no body
    KLIB_UNSUPPORTED_EXTERNAL,    // `external` / JS-intrinsic with no IR body
}
```

Identity remains `IrFunctionSymbol` / official `IdSignature`. FQName is display
only. `SerializedKlibIr.libraryLocation` is the canonical KLIB path from
`KotlinLibrary.libraryFile`, not a reconstructed source path. Offsets on the
deserialized `IrFile.fileEntry` are provenance evidence even after producer
sources are deleted.

## Session split

Do not pretend a JVM FIR session is a KLIB session.

| Session | Entry | Body provider |
| --- | --- | --- |
| `KotlinFrontendSession` | `withKotlinFrontend` / K2 JVM | source module + `BinaryBodies` |
| `KlibSession` | `KlibLoader.withKlibModules` | official `loadIr` / `JsIrLinker` fragments |

`KlibLoader` already exposes official linked `List<IrModuleFragment>` with original
module ownership. The first productionization stage does **not** wire this into
`withKotlinFrontend` or public CLI. Integration must:

1. Keep translated modules as separate fragments; never merge into a fake module.
2. Pass the same list to `EtsBackend.lower(List<IrModuleFragment>)`.
3. Treat JS stdlib as a resolved dependency, not an ETS runtime or emitted module
   unless explicitly selected.
4. Disable partial linkage; missing libraries must produce official diagnostics
   and no target files.
5. Call `checkNoUnboundSymbols` before target lowering.

## Body vs replacement policy

1. If a translated KLIB declaration has a body, provenance is `SerializedKlibIr`.
   Official inlining may consume it when the shared inliner is later given a
   KLIB-backed `FunctionBodies`.
2. If the declaration is in a dependency-only library (stdlib, friends), the
   session may inspect it for closure analysis but must not emit it unless the
   caller selected that library for translation.
3. Missing / external / JS-specific callees remain `Unavailable`. Existing
   `CallRule`s may still replace those calls. Replacement never fabricates IR.
4. JVM serialized IR and KLIB serialized IR are different formats. Do not route
   `.klib` through `BinaryBodies` / `JvmIrDeserializerImpl`.

## Why this file is not an implementation

`FunctionBody.Origin` lives in frozen `Frontend.kt`. Adding `SerializedKlibIr`
requires the shared-contract owner. Independent KLIB infrastructure does not
need that enum to load modules: `KlibSession.linkedModules()` already returns
canonical IR. Closure inspection records signature identity and body presence
without a shared origin type.

## Out of scope

- Public `--klib` CLI.
- Running `JsLoweringPhases` or importing the JS runtime.
- Deleting stdlib `CallRule`s because a KLIB body exists.
- JKLIB / J2CL as a production JVM dependency route (see
  [jklib-future-assessment.md](jklib-future-assessment.md)).
