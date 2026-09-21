# Official KLIB to ETS backend proof

Status: bounded R2.2 proof passes. This is not public CLI KLIB input support,
general JVM bytecode translation, SDK acceptance or completion of R2.

## Reused chain

Pinned Kotlin 2.1.20 compiler and JS stdlib:

```
Real Kotlin sources -> official K2JSCompiler -> three KLIBs
  -> ModulesStructure / CommonKLibResolver
  -> loadIr / JsIrLinker / official declaration and body deserialization
  -> original linked IrModuleFragments
  -> EtsBackend -> typed EtsProgram -> validator -> existing module printer
```

There is no JS text intermediate, copied linker, new expression parser or
synthetic combined IR module. Only `EtsBackend.lower(List<IrModuleFragment>)`
is new production behavior; the existing single-module entry delegates to it.
All selected modules share one language-lowering/symbol session. Original
file/module ownership is preserved, and existing symbol-based module emission
creates the imports. The official compiler owns KLIB dependency resolution,
deserialization, type/signature identity and missing-symbol diagnostics.

Official source references in the pinned compiler sources archive (see
`r2-generic-binary-bodies.md` for archive hash):

- `org/jetbrains/kotlin/ir/backend/js/klib.kt`: `ModulesStructure`, `loadIr`,
  `getIrModuleInfoForKlib`, `getModuleDescriptor`.
- `org/jetbrains/kotlin/ir/backend/js/lower/serialization/ir/JsIrLinker.kt`:
  framework-specific official linker setup.
- `org/jetbrains/kotlin/ir/util/ExternalDependenciesGenerator.kt`: referenced
  symbol resolution, called by `loadIr`.
- `org/jetbrains/kotlin/backend/common/linkage/issues/checks.kt`:
  `checkNoUnboundSymbols`, invoked again before target lowering.

Do not identify every module through `moduleFragmentToUniqueName`: despite its
name, this pinned implementation records only optional `klib.jsOutputName`.
The test selects explicitly approved library paths through the official
resolver, then matches their actual module descriptors by identity. It does not
guess ownership from function names, filenames or JS output names. The JS
stdlib supplies resolved dependencies; it is not indiscriminately emitted.

## Reproduce

From `tools/kotlin-ets`:

```sh
node tests/klib/run.mjs
```

Requires the existing pinned compiler cache, Java, Node and the installed DevEco
TypeScript host used by the other semantic tests. `KOTLIN_JS_STDLIB` may point
to the pinned `kotlin-stdlib-js-2.1.20.klib`; otherwise the existing official-JS
prototype cache is used. The harness records commands, hashes and results under
`tests/klib/.work/run-*` and limits compiler CPU use.

The same fixtures compile for the JVM oracle and KLIB producer. Temporary
producer sources are then deleted before loading, including the consumer source.
The loader receives only the three compiled KLIBs and stdlib. Original source
paths/offsets remain evidence from IR, not a claim those paths still exist.

## Acceptance evidence

- `run-QoHy2F`: retained failed test assertion using the incomplete JS output-name
  map. This was a test ownership-query error, not a loader failure.
- `run-DklY1l`: actual bodies and canonical cross-library symbols verified after
  switching to official descriptor identity.
- `run-MvqSU7`: final frozen full proof. Three modules and five non-inline
  function bodies load, retaining source offsets and canonical call identities.
  Reversing selected modules produces exactly the same ETS files. Strict host
  typechecking resolves all generated imports; original function and parameter
  names are asserted structurally.
- Four JVM/ETS-host result pairs: `Next:9`, `Next:0`, `Explore:15`,
  `Explore:-2147483645`. The last case checks Int overflow, not JS Number math.
- Removing transitive `helper.klib` produces the official missing-library and
  `library -> klibhelper/echo` symbol diagnostic. Partial linkage is disabled;
  no ETS file is produced on that failure.
- Existing source-input module regression `tests/modules/.work/run-TP8ttw`
  passes 44 JVM/module cases, generic/import/visibility checks and no-overwrite,
  filename-collision and partial-output rejection.

`result.json` records frozen implementation/fixture/KLIB hashes, generated ETS
hashes, actual/expected values and evidence levels. This is Node execution of
generated ETS through the DevEco TypeScript host, not ArkVM or native UI proof.

## Production KLIB loader

The proof now calls `dev.ets.dependency.klib.KlibLoader`. That type reuses the
same official `ModulesStructure` / `loadIr` / `JsIrLinker` chain and returns
`List<IrModuleFragment>` with original module ownership. It is still not public
CLI input support.

See [dependency-ir-contract-proposal.md](dependency-ir-contract-proposal.md) for
the proposed `SerializedKlibIr` origin (shared `Contract.kt` / `Frontend.kt`
remain frozen). Collection-body research is in
[klib-collection-body-closure.md](klib-collection-body-closure.md). JKLIB is
assessed separately in [jklib-future-assessment.md](jklib-future-assessment.md).

The remaining production gaps are unchanged: KLIB is not a JVM FIR session, JS
lowerings/runtime are not imported, and KLIB files must not go through the JVM
signature reader.

An output-quality observation remains: deserialized conditional branches can
print an unnecessary constant-true fallback ternary. The tested results match,
but the proof does not claim this formatting has been simplified.
