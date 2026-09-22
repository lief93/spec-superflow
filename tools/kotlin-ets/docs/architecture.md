# Kotlin to ETS backend

This backend translates programs, not selected page snapshots. Kotlin/JS 2.1.20
is the pinned architectural reference. See `kotlin-js-backend-reference.md` for
the exact upstream files and the distinction between reuse and new ETS code.

## Main path

```text
Kotlin source + actual dependency classpath
  -> official K2 semantic analysis and FIR2IR
  -> EtsLoweringPhases (IR-to-IR: source inline, locals/inners, inherited defaults,
     constructor dispatch, secondary constructors, for-loops, string concat,
     expected nullability, generic bounds, capture rebind)
  -> EtsBackend source checks
  -> IrToEts (LanguageLowering + registered CallRule.lower)
  -> typed EtsProgram
  -> target contract validation
  -> module ownership/import assembly and referenced runtime dependency closure
  -> EtsPrinter
  -> ETS source plus required fixed runtime support
```

`EtsBackend.lower` returns a program, not generated text. It must work without
the printer on its runtime classpath. The returned tree must remain usable after
the official compiler environment has been disposed. No Kotlin compiler class,
raw expression string, source parser, or generated JavaScript is a target node.

| Module | Owns | Must not own |
| --- | --- | --- |
| `core/Frontend.kt` | Official compiler configuration, dependency resolution, lifetime; invokes `EtsLoweringPhases` | Phase order, page selection, or target syntax |
| `lower/EtsLoweringPhases.kt` | Ordered IR-to-IR pipeline and `EtsBackendContext` | Target AST construction or JVM codegen |
| `lower/IrToEts.kt` | IR → `EtsProgram` seam (`IrModuleToEts` … `IrTypeToEts`) | High-level Kotlin semantic lowering |
| `core/OfficialLowerings.kt` | JVM-frontend adapter hosting verified official common passes | Running an unvalidated JVM/JS phase chain |
| `core/LibraryInlining.kt` | Select checked source/binary bodies and invoke official inlining/return-block normalization | Inventing bodies from binary signatures or API spelling |
| `core/BinaryBodies.kt` | Load bounded serialized JVM inline bodies with actual provenance and canonical symbols | Treating signatures as bodies or inventing missing dependency implementations |
| `core/LocalDeclarations.kt` | Invoke official capture/lifting passes with typed ETS shared cells | Reimplementing capture analysis or importing JVM/JS runtime cells |
| `core/ForLoops.kt` | Invoke official common loop lowering and normalize generated generic call types | Re-parsing source loops or assuming arbitrary iterators are arrays |
| `core/Backend.kt` | Source checks and ordered backend assembly | String-based expression rewriting |
| `language/` | Types, lexical symbols, methods/models, control flow, evaluation order, closures | Formatting, preview state, library-name guesses |
| `stdlib/` | Resolved library-call semantics and reusable target runtime helpers | A second expression parser or evaluator |
| `target/Tree.kt` | Compiler-independent types, symbols, declarations, expressions, statements, origins | Executing the source program |
| `target/Validator.kt` | Target contract checks before output | Replacing Kotlin's semantic analyzer |
| `target/TypeSubstitution.kt` | Substitute target generic types by binder identity | Inferring source types again or matching type-parameter names |
| `target/Traversal.kt` | Exhaustive structural traversal shared by dependency consumers | Selecting only the currently previewed branch |
| `target/Printer.kt` | Parentheses, escaping, indentation, target source syntax | Calls into Kotlin IR, adapters, or preview evaluation |
| `output/Modules.kt` | Per-source-file output, symbol/type imports, required runtime support | Re-parsing printed expressions or renaming collisions silently |
| `ui/` | Compose framework adaptation using the shared language interface | Independent handling of general Kotlin expressions |

## Contracts

The current shared API and lane ownership are fixed in
[shared-contracts.md](shared-contracts.md). These are production boundaries with
contract tests, not additional compiler frameworks.

- Source bindings use official IR symbols, not parameter-name matching.
- Target bindings reference an `EtsSymbol` with identity, display name, type and
  source location. Compiler temporaries can receive generated names; ordinary
  names remain unchanged when supported by the target.
- Source-class types carry declaration IDs. Generic type references carry binder
  IDs distinct from their display names. Call-site substitution uses the official
  frontend's resolved type arguments; it does not infer them from target text.
- Every expression has a target type and source span. Lowering chooses target
  operators or runtime calls before formatting begins.
- `CallRule.lower` returns a typed node or declines the call. Language lowering
  checks an accepted result against the mapped source result type. No adapter
  returns an arbitrary target expression string.
- A discarded call and a value-producing call use the same expression lowering,
  but only the discarded context may use `CallRule.lowerStatement`. Storing or
  returning a value cannot use that hook to substitute a void effect for an
  object. Implicit Kotlin Unit coercion is an explicit discarded context;
  `etsDiscard` preserves single execution while producing a typed void result.
- The printer cannot select a condition, evaluate a default, invent a missing
  argument, or drop a branch. Those would change the program, not its syntax.
- Static runtime helper source is a tested target dependency, not generated
  source recovered by parsing strings. Existing numeric/list/string helpers
  remain shared implementations called by typed target nodes.

## Parallel ownership

Work is parallel by architectural responsibility, with one shared contract:

1. Official frontend, dependency bodies and verified common passes.
2. Language lowering and existing language semantics.
3. Standard-library call lowering and runtime semantics.
4. ETS target tree, validation, output and typed UI integration.

Contract and differential tests gate all four lanes; they are not a substitute
for the frontend/dependency lane. Shared changes have one integration owner.

The current bounded increment is recorded in [parallel-batch-20260914.md](parallel-batch-20260914.md).
It does not add controls or repair a specific screenshot. Changes to shared
target nodes are coordinated by the core owner before other modules use them.

## Current limits, not future claims

This batch establishes the language target tree and migrates the existing
bounded language/library support. It does not import the complete Kotlin/JS
lowering pipeline, implement all Kotlin semantics, or make arbitrary JVM
dependencies available on HarmonyOS. Common compiler passes require separate
compatibility experiments before reuse. The first such experiment, common string
concatenation lowering, is now integrated; see `official-lowering.md`.
In particular, loading inline library
bodies is different from reading a JVM method signature.

The existing bounded Compose adapter now returns `EtsProgram` throughout:
controls/children/attributes, loops/conditions, fields/builders, slots and event
callbacks. `UiTextModule` and the independent UI text emitter were removed.
The same validator, traversal and printer handle language and UI nodes. Fixed
typography/touch implementations are explicit framework runtime dependencies.
This completes the representation migration, not support for all Compose APIs.

Non-reified invariant generic functions and simple generic classes now have a
bounded tested path, including generic member/accessor substitution. Explicitly
supplied source-library bodies use official inlining. Language mode supports
flat per-source-file output with symbol-based imports. See `generics.md`,
`library-inlining.md` and `module-output.md` for exact boundaries.

Named local functions now use official shared-variable and local-declaration
lowering, with typed ETS cells for shared mutable captures. Ordinary closures
without named locals keep their existing path. See `local-declarations.md`.

Int ranges and supported stepped progressions now use official common
`ForLoopsLowering`, preserving per-iteration closure bindings and loop control.
Typed `filter/filterNot` calls use a reusable array-backed collection runtime.
See `loops.md` and `collection-filter.md` for supported shapes and rejected cases.
Multi-file output now checks exported value/type dependencies and import-name
collisions before requesting runtime output, without inventing import aliases.

The bounded binary loader now supplies actual SourceFile metadata to the official
deserializer/inliner. Serialized top-level non-generic inline bodies have a real
CLI/JVM differential path. Missing bytes, provenance or required linked symbols
reject before output. See `binary-bodies.md` for compiler evidence and limits.

General binary dependency graphs/KLIB loading, broader generic variance/projection
semantics, full iteration/stdlib coverage, local classes and uninitialized captured variables,
inheritance/interfaces/overloads, coroutines, broader
runtime semantics and broader Compose adaptation remain separate work.
Residual local function declarations fail closed because ArkTS does not support
nested function declarations or generic arrow functions. Ordinary supported
closures remain typed lambdas.

## Acceptance order

1. Target AST/printer tests, compiled without Kotlin compiler dependencies.
2. Official-IR lowering tests running without the printer.
3. Existing non-Compose source/target behavior and negative-case tests.
4. SDK compilation of generated language/library modules, where available.
5. Existing Compose code-generation regression checks only.

Page installation, screenshot comparison and new page-specific fixes do not
drive this architecture batch. The previous native run is frozen separately;
its incomplete visual acceptance is not evidence that this architecture passes.
