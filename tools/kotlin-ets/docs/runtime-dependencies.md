# Runtime Dependencies

## Implemented Boundary

Language-mode CLI output collects runtime requirements from the complete validated
`EtsProgram`, before printing. `standardLibrarySupportLines(program: EtsProgram):
List<String>` returns only selected static declarations, once per output module.
An empty selection adds no prelude or prelude separator. This is runtime selection,
not dead-code elimination of source declarations: all emitted function bodies
remain roots, including functions not called by another source function.

`StandardLibraryDependencies.kt` traverses every sealed target-node form, including
callee and argument expressions, member receivers, parameter defaults, field
initializers, nested functions, lambdas, constructor/method/accessor bodies,
branches and loops. Function kinds are not filtered. Collection is local to one
program; file order and reference discovery order cannot change runtime order.

Only external `EtsReference` symbols in the existing `stdlib:` identity namespace
request runtime declarations. The symbol name must agree with its ID. Local
symbols, unrelated external IDs and literal strings cannot request helpers.
`stdlib:Math` denotes the native host object and needs no emitted declaration.
Unknown stdlib IDs or inconsistent names reject output rather than silently leave
an unbound helper. This does not replace the target validator's type checks.

## Static Runtime

`StandardLibrarySupport.kt` holds the same seven fixed helper bodies as before,
separated into declarations with their exact external symbol IDs. The only current
helper-to-helper edge is:

```text
stdlib:__etsSubstringFrom -> stdlib:__etsSubstring
```

All other helpers have no emitted-runtime dependencies. Native `Math`, `Error`,
array members and string members are supplied by the target environment. The
selection computes this small closure and filters a fixed dependency-first order:
IntDiv, IntRem, ListGet, ListAdd, ListMap, Substring, SubstringFrom. Each declaration
appears at most once. No input-dependent source generation, output-text scanning,
new API mapping, library loader or generalized linker is introduced.

The zero-argument `StandardLibraryRules.supportLines()` API remains intentionally
unchanged. `Main.kt` page mode still consumes it because `ComposeEmitter.emit`
returns `UiTextModule`, not a complete typed tree. That path still emits all seven
helpers; claiming page-mode tree shaking would be incorrect. Removing this real
consumer's fallback requires a separate typed UI dependency interface, not regex
inspection of its output. No UI-specific workaround is part of this change.

## Official Kotlin/JS Reference

This adapts the reference-and-closure pattern, not Kotlin/JS implementation code:

- Kotlin v2.1.20 [UsefulDeclarationProcessor.kt, lines 31-46 and 79-100](https://github.com/JetBrains/kotlin/blob/v2.1.20/compiler/ir/backend.js/src/org/jetbrains/kotlin/ir/backend/js/dce/UsefulDeclarationProcessor.kt#L31)
  follows resolved declaration accesses and enqueues unseen dependencies;
  [lines 209-240](https://github.com/JetBrains/kotlin/blob/v2.1.20/compiler/ir/backend.js/src/org/jetbrains/kotlin/ir/backend/js/dce/UsefulDeclarationProcessor.kt#L209)
  process roots and referenced bodies to a fixed point.
- [IrModuleToJsTransformer.kt, lines 204-220](https://github.com/JetBrains/kotlin/blob/v2.1.20/compiler/ir/backend.js/src/org/jetbrains/kotlin/ir/backend/js/transformers/irToJs/IrModuleToJsTransformer.kt#L204)
  optimizes production IR before generating output;
  [lines 509-535](https://github.com/JetBrains/kotlin/blob/v2.1.20/compiler/ir/backend.js/src/org/jetbrains/kotlin/ir/backend/js/transformers/irToJs/IrModuleToJsTransformer.kt#L509)
  retain declaration-tag identity for name bindings and imports.

Those components require JS backend context, IR declarations and JS module
fragments. They are not directly reusable over this ETS tree. This bounded
implementation uses the already-established `EtsSymbol.id` and a fixed seven-body
catalog instead; it neither duplicates the official DCE framework nor claims to
execute official JS lowering. Official common-lowering work remains separate.

## Reproduction

From the repository root:

```sh
node tools/kotlin-ets/tests/stdlib/check-runtime-dependencies.mjs
bash tools/kotlin-ets/tests/stdlib/check-runtime-tree.sh
bash tools/kotlin-ets/tests/stdlib/check-symbols.sh
bash tools/kotlin-ets/tests/stdlib/check-public-cli.sh
```

The first command uses fresh public CLI outputs for no-runtime, division-only,
cross-file class/function/lambda, substring transitivity and repeat determinism.
It checks declarations using TypeScript AST, executes the generated module and
retains each CLI stdout/stderr plus `result.json` in the announced `.build` folder.
String content resembling helper names is deliberately not a dependency.
The Kotlin structural test isolates every child position, including all current
function kinds, and checks symbol identity, deduplication, multi-file ordering,
invalid runtime IDs and the UI compatibility API. Synthetic traversal nodes are
not substitutes for the genuine-compiler CLI/runtime cases.

`tests/stdlib/check-sdk.mjs` also asserts the expected helper subsets for the
existing Scalars and Lists modules before staging unchanged generated bytes in
the isolated SDK host. SDK execution belongs to the integration owner for this
batch; no SDK/device run or independent review is included here.
