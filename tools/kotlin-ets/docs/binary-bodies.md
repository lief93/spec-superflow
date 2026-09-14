# Serialized JVM inline bodies

This records the initial binary-body vertical slice. The current R1 transitive
extension and its separate evidence are in [r1-binary-reachability.md](r1-binary-reachability.md).

## Production route

`withKotlinFrontend` supplies one checked `FunctionBodies` provider for source
and bounded binary dependencies. `BinaryBodies.kt` reads only the binary class
attached to the actual resolved FIR declaration. Ordinary JAR signatures still
do not count as bodies. No library source is passed to the binary CLI consumer.

The supported vertical slice is an ordinary, non-generic top-level inline
function in a JVM file facade built by Kotlin 2.1.20 with `-Xserialize-ir=inline`,
including defaults, named-argument evaluation order and lambda/captured effects.
This is not a general JVM or KLIB linker.

1. Read `JvmPackagePartSource.knownJvmBinaryClass` and its actual serialized IR.
2. Read that `VirtualFileKotlinClass.file` with the compiler's ASM visitor.
   Require the real `SourceFile` attribute, never a name inferred from a method,
   facade, caller or source archive.
3. Register the actual resolved functions and signature classifiers/methods in
   the real symbol table with official `PublicIdSignatureComputer` and
   `JvmIrMangler`. Check existing declaration identity on every registration.
4. Use the official facade factory and `JvmIrDeserializerImpl` with the real
   frontend builtins, symbol table and providers. No body is constructed by ETS.
5. Require no unbound symbol-table dependencies, preserved resolved signature
   types, actual requested bodies and supported referenced calls. Abort rather
   than handing partially linked IR to emission.
6. Supply the same declaration and loaded body through `FunctionBody.Available`.
   The production common inliner consumes that provider, then the existing
   official normalization passes run.

The provenance file is not added to input source-module files or emitted as a
source class. The JVM facade is a compiler-side parent only. All compiler objects
remain borrowed inside the frontend callback.

## Honest source identity

Example identity:
`.../serialized.jar!/binarylibrary/BinaryLibraryKt.class#SourceFile=BinaryLibrary.kt`.
This is actual binary metadata, not a claim that source text exists at that path.
`supportsDebugInfo=false`; unknown lines, columns and maximum file offset remain
`-1`. No line table is invented.

Official deserialization reuses the bound FIR stub and keeps its unknown
declaration offsets. The body itself has real serialized offsets: `114..185` for
the fixture. `Available.source` uses that actual body span. The declaration is
not replaced merely to manufacture offsets.

The earlier experiment failed at `FunctionInlining.kt:304` because the callee's
external-package parent had no `fileEntry`. The production implementation now
provides the class's actual SourceFile identity, not a fabricated caller file,
and reaches real official inlined blocks.

## Checks

From `tools/kotlin-ets`:

```sh
node tests/binary-bodies/run.mjs
```

The harness sets `JAVA_TOOL_OPTIONS='-XX:ActiveProcessorCount=2 -XX:+UseSerialGC'`
and records commands/status/output, JAR hashes, production IR, body provenance
and JVM/target results. It checks:

- A genuine ordinary JAR rejects with a missing-serialized-IR message, caller
  source span and no target.
- A genuine serialized JAR yields two official `IrInlinedFunctionBlock`s with
  the same actual function symbol, defaults, parameter names, canonical Int
  identity and binary provenance. No binary inline calls remain. The borrowed
  body resolver rejects access after the callback closes.
- Removing only `SourceFile` from a genuine JAR rejects before emission. Body
  bytes alone are not accepted as source identity.
- A real inline library calling a non-serialized `@PublishedApi` helper rejects
  with the exact unlinked `hiddenOffset` signature; no helper body is invented.
- Public CLI takes application source plus the serialized JAR, without dependency
  source. DevEco TypeScript/Node execution is compared with the same application
  compiled/executed on the JVM against that JAR. Expected results are
  `45:16:7:4:BALD` and `129:23:14:11:BALD`.

`--evidence-only` runs producer/frontend checks without public CLI/target
generation when other lanes are changing the output backend. That mode explicitly
does not claim end-to-end success.

Current evidence under `tests/binary-bodies/.work/`:

- `policy-htbUTP/red-cli.stdout`: public CLI RED, actual exit 2 on a real
  serialized JAR while the new expectation requires target output. The separate
  earlier producer timeout in that directory is not counted as RED.
- `policy-lvjjMT`: frontend positive and both incomplete-dependency cases pass,
  exit 0.
- `policy-QHbjx7`: full `node tests/binary-bodies/run.mjs`, exit 0. Three public
  CLI negatives return expected exit 2 and no target; actual binary-only CLI,
  production IR evidence and both JVM/Node results pass. Binary provenance uses
  body offsets `114..185`; negative diagnostics use application offsets
  `339..501`.
- `policy-xeINaX` and `policy-pokLBC`: concurrent UI/stdlib compilation failures
  retained, not misreported as binary semantic failures or GREEN.

The additional existing `tests/inline/run.mjs` regression initially failed at
`run-nwHjg6/evidence-build.json` because its explicit frontend list omitted new
`BinaryBodies.kt`. After the main integrator updated that list, `run-0UeDN4`
passed with exit 0: 10 official inline blocks, 3 source-library blocks, no
remaining returnable blocks, source-backed CLI/JVM differential and the ordinary
binary-only JAR rejection. Main owns final SDK integration and has the exact
`policy-QHbjx7/binary-backed.ets` below; no SDK pass is claimed by this lane yet.

Production freeze SHA-256:

- `src/core/Frontend.kt`: `d9f34b9ffc94494ce84a37f204cdfcf7a49cff4f67a03436f1f937f42eae9597`
- `src/core/LibraryInlining.kt`: `7bb29b03e1f29047451060cd322011907a6171c37f5e7c30f51c4daeadcc9fc0`
- `src/core/BinaryBodies.kt`: `d9db9d558a87ebe1fc1f132783c2d93fbdb4c419b001e9d0bf77d6902832f28f`
- Exact generated `policy-QHbjx7/binary-backed.ets`: `4902fadc022797dc68a2efac3cb435eb9e29b38d32cfc795c335b2135fcb7499`

`BinaryProbe.kt` and `experiment.mjs` retain the earlier raw-deserializer
experiment. They do not use the production provider; their expected `Unknown
file` is historical, not the current implementation status.

## Official references

Pinned source archive:
<https://repo.maven.apache.org/maven2/org/jetbrains/kotlin/kotlin-compiler-embeddable/2.1.20/kotlin-compiler-embeddable-2.1.20-sources.jar>

Source SHA-256: `dc1ec1391e465b56d7e664fcf63d0ff4cfeb7274fc6e2b0dbd71335f8ce1dc11`.
Compiler SHA-256: `c54a00718c8c0e3ee858bf42771c7f401c5e3c1738861e18e9536371042fa1b3`.
Paths below are relative to `org/jetbrains/kotlin/` in that archive.

| Official implementation | Use/boundary |
| --- | --- |
| `cli/common/arguments/K2JVMCompilerArguments.kt` | Actual `-Xserialize-ir=inline` producer flag |
| `backend/jvm/serialization/JvmIrSerializerSession.kt` | Serializes real bodies, types and signatures into the JAR |
| `load/kotlin/VirtualFileKotlinClass.kt` | Actual resolved binary bytes/location, no source-by-name lookup |
| `backend/common/serialization/signature/IdSignatureComputers.kt`, `ir/backend/jvm/serialization/JvmIrMangler.kt` | Official public signatures for actual declaration registration |
| `backend/jvm/JvmFileFacadeClass.kt`, `backend/jvm/lower/ExternalPackageParentPatcherLowering.kt` | Official facade creation/parent pattern |
| `backend/jvm/JvmIrDeserializerImpl.kt` | Production official deserializer, not a copied implementation |
| `backend/jvm/serialization/deserializeLazyDeclarations.kt` | Existing-symbol loading/dependency generation; dummy unknown file alone is insufficient provenance |
| `backend/common/serialization/IrDeclarationDeserializer.kt` | Reuses bound declarations and loads real parameters/defaults/body |
| `ir/inline/FunctionInlining.kt` | Production common inliner consumes loaded declaration/file identity |

## Remaining boundaries

Generic/member binary inline declarations, non-file-facade formats, constructors
inside binary bodies, unlinked/transitive library dependencies and arbitrary
helpers are rejected or unavailable. Canonical registration is a bounded bridge
to existing FIR symbols, not a general dependency provider. The whole loaded
facade must link: unsupported unused serialized siblings can prevent loading.

Other compiler versions, KLIBs, source archives and arbitrary JVM-only operations
are not claimed. The official deserializer also runs
`SingletonObjectJvmStaticTransformer`; the accepted subset excludes that object
and constructor expansion rather than calling the entire JVM deserializer
target-neutral. SDK results are separate from Node execution. No device work,
review or commit is part of this lane.
