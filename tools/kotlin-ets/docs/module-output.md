# Multi-file ETS Output

Language mode accepts exactly one output form:

```sh
bash tools/kotlin-ets/kotlin-ets --mode language \
  --out-dir /tmp/new-ets-modules \
  tools/kotlin-ets/tests/modules/Model.kt \
  tools/kotlin-ets/tests/modules/Numbers.kt \
  tools/kotlin-ets/tests/modules/Entry.kt
```

`--out` retains the single-file form. `--out-dir` emits one flat `.ets` file per
source basename. The destination must not exist. There are no source-package
subdirectories, generated alias names, or migration runtime directories.

## Ownership and Dependencies

The official frontend resolves source declarations and calls. Language lowering
retains those identities in function references and source-class types. The
output assembler maps declaration IDs to their owning `EtsFile`, traverses the
typed tree, and creates explicit relative imports for cross-file references.
It does not match method names, scan printed code, or infer types from spelling.

The traversal includes function signatures, generic bounds and arguments, local
types, defaults, field initializers, nested closures, calls and constructor
types. Runtime helpers are selected independently for each emitted module,
including helper-to-helper dependencies. No source dead-code elimination is
claimed: an emitted but unused function still needs its dependencies.

All source lowering, target validation, filename checks, dependency assembly and
printing complete before creating the output directory. Unsupported source does
not leave a partially generated directory. Existing destinations are never
overwritten, including dangling symlinks. This is not a transactional guarantee
against disk or process failure during writing.

Module namespace validation is separate from single-file validation. Different
files may keep the same declaration name when their own references are
unambiguous. An import that would collide with a local declaration or another
import fails with the reference's source span; no automatic alias is invented.
Cross-file value and type references require the target declaration's `exported`
flag. All module plans pass these checks before any runtime provider is called.

## Official Reference

Kotlin 2.1.20's `IrModuleToJsTransformer.generateProgramFragment` records per-file
definitions, name bindings and imports. `computeAndSaveImports` uses declaration
signatures rather than printed identifiers. This is the reference for the ETS
ownership/dependency stage; the JS AST, wrappers, JS-specific naming and DCE are
not executed on ETS.

Reference: `compiler/ir/backend.js/src/org/jetbrains/kotlin/ir/backend/js/transformers/irToJs/IrModuleToJsTransformer.kt`
in the pinned Kotlin 2.1.20 source archive. The ETS-specific implementation is
`src/output/Modules.kt`; it consumes the same typed tree as the printer and
runtime dependency collector.

## Boundaries and Verification

- Case-insensitive source-basename collisions are rejected, not renamed.
- The single-file output still rejects duplicate top-level names. Multi-file
  output checks names per file and rejects ambiguous generated import bindings.
  Package alias generation and Kotlin overload export policy remain separate work.
- Supported source declarations use the backend's existing explicit exports.
  This is not a complete Kotlin visibility or binary module ABI implementation.
- Page mode still uses its transitional text envelope and does not accept
  `--out-dir`.
- Binary dependency body loading is not supplied by module assembly.

Public CLI tests: `node tools/kotlin-ets/tests/modules/run.mjs`.
They compare Kotlin/JVM results with generated modules executed through the
installed DevEco TypeScript host toolchain, and check imports and failure output.
The fixture includes different same-named private Kotlin helpers in two files;
their target methods keep their names and distinct results. This does not change
the existing export policy into a complete Kotlin visibility implementation.

`bash tools/kotlin-ets/tests/modules/contract.sh` checks target namespace/export
invariants independently of the Kotlin compiler, including type-only imports,
colliding imports and failure before runtime emission. Initial RED:
`tests/modules/.work/contract-rqOmPn`; focused GREEN:
`tests/modules/.work/contract-yvdqKY`.

SDK verification: `node tools/kotlin-ets/tests/modules/sdk.mjs <successful-modules-run> <successful-inline-run>`.
This compiles the unchanged generated `.ets` modules in a cloned Harmony project,
checks the compiler input records and produced ABC/HAP, and records hashes.
The host also imports the generic cross-file fixture and official-inliner output
to exercise the three architectural lanes together. Module generation and SDK
verification must use the same unchanged backend implementation.
Host execution and actual ETS compilation are separate evidence, not a claim of
ArkVM/device execution or visual equivalence.
