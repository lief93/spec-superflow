# Kotlin/JS Backend Reference For The ETS Architecture

## Scope And Provenance

This is a read-only architectural study of official Kotlin **v2.1.20** sources,
not a Kotlin/JS-to-ETS implementation or permission to resume UI feature work.
The intended ETS pipeline remains Kotlin/JVM in memory: official resolved K2 IR,
shared language lowering, structured target nodes, then target printing. Emitted
JavaScript is not an intermediate representation for ETS.

The implemented code reuses the official K2 frontend/FIR2IR pipeline on the JVM.
The official JS backend lowerings described below are research references only:
this integration does not reuse or claim to run their complete lowering pipeline.

Evidence comes from the nine locally cached files in
[`official-backend/`](../../../artifacts/kotlin-js-official-prototype-20260913/official-backend/).
The authoritative [index](../../../artifacts/kotlin-js-official-prototype-20260913/official-backend/index.json)
records each pinned upstream URL, raw download URL, metadata URL, Git blob SHA-1,
SHA-256, and byte count. On 2026-09-13, all nine local files were independently
checked against the recorded byte count and SHA-256, and against Git blob SHA-1
using `SHA1("blob " + byteCount + NUL + bytes)`. All matched. No source was
downloaded, cache updated, compiler run, or native build/device operation performed
for this document. Hash agreement verifies the cached bytes against that index;
it is not a new upstream signature or release verification.

The following URLs resolve to **v2.1.20**, not a moving default branch. Paths are
relative to the cached `official-backend/` directory.

| Reference / Cached Path | SHA-256 From Index |
| --- | --- |
| [P: JsLoweringPhases.kt][P] | `06a16a7c77cdccf0fbcdd91e2a0649d4990b4392570a0ae4cb0b7ae78a1602de` |
| [O: optimizations.kt][O] | `bd73e293d637416abb2968086e9867f59225bc7559341acd6e07a03bd603029e` |
| [M: transformers/irToJs/IrModuleToJsTransformer.kt][M] | `a87e02ab8e14aacff2aaf11744c154cf2cf4ef57e8b04ce42c9b09421659c898` |
| [F: transformers/irToJs/IrFunctionToJsTransformer.kt][F] | `a88f14350d29e6ed82b224f4da185a93e1dcbbabe4b324bbc3f13713db2e0d34` |
| [E: transformers/irToJs/IrElementToJsExpressionTransformer.kt][E] | `a8d9f69cddbf82298b8ffd29b87069a045799c0ffaa0eb64ee62cc99c7a1144d` |
| [S: transformers/irToJs/IrElementToJsStatementTransformer.kt][S] | `d29fae7c7b84c5a98798dae117c521919ec410db7b335d487f7178b3e505351d` |
| [C: transformers/irToJs/JsClassGenerator.kt][C] | `78e05cb06cc5ad5c6c38b8bf5252978caed4760d84609b08a143de962000f775` |
| [D: lower/JsDefaultArgumentStubGenerator.kt][D] | `6cef8b752f8836a4bd107963f36a5a4c8d777ac298976c9110c81268a8bf39e6` |
| [N: lower/calls/NumberOperatorCallsTransformer.kt][N] | `e61de2322f6a2a24716556b0b91c3da109ef1e114863745e117abcf3d844d763` |

## Four Distinct Boundaries

```text
Resolved Kotlin IR + JS backend context/configuration
    -> ordered IR-to-IR lowering and validation
    -> irToJs visitors construct JS AST/program fragments
    -> AST optimization, fragment/module merging, name resolution
    -> JS AST printer produces code and optional source maps
```

This diagram describes the boundaries visible in the cached sources, not the
complete frontend/KLIB/linker entry sequence. In particular, module generation
also performs static-member lowering and optional IR optimization; it is not a
pure serialization call. [M, lines 190-233][M-module]

### 1. Ordered IR Lowering

`getJsLowerings(configuration)` returns an ordered list of
`SimpleNamedCompilerPhase<JsIrBackendContext, IrModuleFragment, IrModuleFragment>`.
`getJsPhases` packages that list as `IrModuleLowering`. These phases transform IR;
they do not return source strings or JS AST expressions. The list includes
validation, shared-variable handling, inlining, local declarations, properties,
coroutines/continuations, default arguments, type operators, inline classes,
autoboxing, block decomposition, calls, and cleanup. Configuration can change
which inlining/accessor phases are present. [P, lines 744-877][P-order]

The prerequisites are substantive. Local declarations depend on shared-variable
and local-delegated-property lowering; default-argument override patching depends
on stub generation; block decomposition depends on type-operator and suspend
lowering. Selecting a pass merely by its attractive name is not enough.
[P, lines 413-427, 502-527, 624-638][P]

Default arguments illustrate target-specific semantics inside an IR pass.
`JsDefaultArgumentStubGenerator` extends the common generator with a JS factory,
uses `context.getVoid()` to distinguish an omitted value, copies assignable
parameters, remaps parameter references, and inserts default-resolution
assignments into the body. It also handles generated dispatch stubs. This is
not just printing `parameter = expression`. [D, lines 33-137][D-defaults]

Numeric operators likewise become resolved intrinsic calls. The numeric
transformer consults operand/result types, adds Int32 coercion where applicable,
uses `jsImul` for Int multiplication, and routes division/remainder through JS
intrinsics. Its `toInt32` builds a `jsBitOr` IR call with zero. These are JS target
choices, not permission for an ETS printer to discover numeric semantics from an
operator spelling. [N, lines 25-27, 140-190, 308-313][N-numbers]

### 2. IR-To-JS AST Construction

Expression, statement, and function visitors return `JsExpression`,
`JsStatement`, and `JsFunction` respectively, with `JsGenerationContext` supplying
symbol-derived names and backend services. For example, value reads use the
declaration symbol to obtain a reference; assignments build AST operations;
short-circuit `IrWhen` origins become AND/OR operations, while general expression
branches become conditionals. Source metadata is attached through `withSource`.
[E, lines 27, 111-174, 239-280][E-expressions]

Statement conversion reuses expression conversion through `makeStmt()`; it is
not a second implementation of expression semantics. Break/continue obtain
names from their actual IR loop targets. Function conversion separately chooses
static, member, local, or constructor names before `translateFunction`.
[S, lines 31-101][S-statements]; [F, lines 17-37][F]

These visitors expect prior lowering. The expression visitor rejects unlowered
Long/Char constants and most type operators, and requires non-external object
reads to have been lowered. The statement visitor rejects function declarations
encountered through its general function visitor. Passing our pre-Compose,
JVM-frontend IR directly to these visitors does not meet these invariants.
[E, lines 68-87, 151-159, 273-280][E]; [S, lines 33-37][S]

Class generation is target-specific too: it chooses ES5/prototype versus ES6
paths, emits accessor forwarding and metadata, and records pre/post-declaration
blocks. It is not a generic Kotlin-class-to-ArkTS-class converter.
[C, lines 36-64, 94-135, 181-263, 378-406][C]

### 3. AST, Optimization, And Assembly

`generateProgramFragment` constructs a naming table, `JsNameLinkingNamer`, and
`JsStaticContext`, then asks `IrFileToJsTransformer` for AST statements. The
fragment retains declarations, class models, initializers, imports, definitions,
name bindings, and optional export/test information. This is more than a list of
already-printed function bodies. [M, lines 404-487][M-fragments]

IR optimization and JS AST optimization are separate operations.
`optimizeProgramByIr` performs dead-declaration elimination and optimization IR
passes. `optimizeFragmentByJsAst` visits functions/classes and applies JS
post-processors. Module generation runs IR optimization for production modes;
fragment generation conditionally runs AST optimization. Neither is equivalent
to pretty-printing or evidence that arbitrary source locals may be duplicated.
[O, lines 21-57][O]; [M, lines 204-220, 483-485][M]

Here, "AST" means structured JVM objects such as `JsInvocation`, `JsConditional`,
`JsFunction`, and `JsClass`. It does **not** mean a target AST retaining the Kotlin
type system or emitting ArkTS type annotations. The module transformer separately
creates optional TypeScript export fragments and returns them alongside JS code.
That `.d.ts` path is not an ETS implementation backend.
[E][E]; [C][C]; [M, lines 249-259, 679-685][M]

### 4. Output Printing

`generateSingleWrappedModuleBody` merges fragments with module/cross-module
information, resolves temporary names, creates `TextOutputImpl` and an optional
source-map consumer, then calls
`program.accept(JsToStringGenerationVisitor(...))`. The result contains JS text,
optional source-map text, optional TypeScript fragments, and optionally the AST.
String production is a final boundary, not the expression visitor's return type.
[M, lines 635-687][M-output]

The cache contains this printer invocation, **not** the implementation of
`JsToStringGenerationVisitor`, `Merger`, `JsGenerationContext`, the AST node
classes, or temporary-name resolution. Their detailed precedence, escaping,
binding, and source-map behavior has not been audited from this nine-file set.

## Reuse Assessment For ETS

| Area | Useful Reference | Constraint Before Implementation Reuse |
| --- | --- | --- |
| Ordered semantic passes | Explicit inputs, prerequisites, validation, and IR origins | Audit each pass's context, symbols, mutations, and runtime assumptions; the "Common Native/JS/Wasm prefix" label does not establish ETS compatibility. |
| Expression/statement split | Statements delegate expression construction to one implementation | Use the shared ETS language lowerer; do not copy JS visitors into UI as a second language backend. |
| Symbol/name management | Declaration identities, lexical contexts, loop targets, temporary names | Preserve source boundaries and shadowing under ETS rules; JS export/member mangling is not the required source ABI. |
| Default/numeric semantics | Resolved-type dispatch and deliberate lowering | Adapt to the selected Kotlin/JVM-to-ETS contract and runtime; prove effects, defaults, overflow, and exceptional cases independently. |
| AST construction | Explicit node categories and source metadata before printing | JS nodes do not supply ETS types, ArkUI Builder syntax, native imports, or a target legality checker. |
| Optimization | Separate IR and AST transformations | Require effect/liveness proof; do not drop an unused effectful initializer or duplicate a stateful getter. |
| Output assembly | Structured imports, declarations, naming, and final printing | ETS requires its own module/layout grammar and printer; do not hoist imports or reconstruct expressions by regex over generated text. |

`JsIrBackendContext` is not a generic `IrModuleFragment` wrapper. The cited code
requires JS intrinsics, configuration/module kind, inline-class support, export
state, naming services, and runtime-related metadata. These services are accessed
both by lowerings and by AST generation. A JVM frontend object graph with Android
classpath symbols cannot be made into valid JS-backend input just by inventing
a context or replacing the final printer. [D][D]; [N][N]; [E][E]; [M][M]

The existing [official JS experiment](../../../artifacts/kotlin-js-official-prototype-20260913/README.md)
is supporting runtime evidence, not ETS acceptance: its recorded JVM and Node
runs agree on one program's 12 checks; its unmodified `java.time.LocalDate` source
fails Kotlin/JS compilation. Its
[comparison summary](../../../artifacts/kotlin-js-official-prototype-20260913/comparison-summary.json)
records the versions, hashes, and results. These runs were not repeated for this
study. They do not establish arbitrary Android/Compose compatibility, Kotlin/JVM
exception equivalence, or native rendering correctness.

## UI Expression Boundary

The manager-owned contracts now live in `src/target/Tree.kt` and
`src/core/Contract.kt`. `Language.type`, `expression`, `statements`, `function`,
and `clazz` return typed nodes; `Language.source` supplies source spans.
`EtsPrinter` prints types/expressions to strings and statement/function/class
nodes to lines. The UI integration uses that shared printer, not a second
language implementation.

```text
Official K2 IR
  -> shared language lowering + resolved stdlib/platform call rules
  -> structured target type/expression/statement/function/class nodes
  -> ONE shared language printer
  -> temporary text UI envelope / final ETS module assembly
```

UI may temporarily print its native component/Builder envelope as text. Every
embedded language expression, callback body, parameter type, ordinary function,
and class must nevertheless come through the same shared lowering and printer
used outside UI. `Scope.bindings` and `Scope.callRule.lower` must carry structured target
values/expressions, not emitted code strings. State/field/pager overrides must
construct target nodes rather than hide source-language operations inside text.

There is no `RawExpression` escape hatch. A missing node or unsupported operation
requires an explicit contract extension or a source-linked rejection, not a
string disguised as an AST expression. Formatting, quoting, precedence, and
parenthesization belong to the shared printer; evaluation order, single
evaluation, defaults, state access, and control-flow semantics belong to lowering.
The expression result is an `EtsExpression`, without a separate prerequisite
statement list. UI must not invent a private statement-expression convention.
Source-local single-evaluation bridges are retained at the existing Builder
boundary. State reads/writes and pager adapters construct member, assignment,
and call nodes. A state setter discards the assignment value through shared
`etsDiscard`, a typed void IIFE, rather than mislabeling its type. The separate
`CallRule.lowerStatement` is effect-only: a supported UI launch becomes a native
pager call statement, while using its source `Job` result remains unsupported.
Source bindings use `EtsReference`/`EtsSymbol` identity and spans;
content bindings use `EtsNamedType("WrappedBuilder", [EtsTupleType([])])`
(schema notation, not Kotlin constructor syntax).

`UiTextModule` deliberately names the remaining transitional text envelope.
Its native component tree, Builder declarations, slots, and platform support
templates are not yet an `EtsProgram`. This work does not claim a unified typed
UI AST or whole-page target validation.

Do not run mutating JS lowerings over the shared UI input opportunistically.
Inlining, local declaration extraction, property lowering, and name changes can
erase the resolved Compose calls and source wrapper boundaries that UI needs.
Any proposed common-pass reuse needs an explicit IR stage, ownership/isolation
rule, preconditions, and source-boundary tests before it is enabled.

## Remaining Gaps And Gates

- The typed expression/statement/declaration contract is available, but native
  UI nodes and the transitional `UiTextModule` envelope still need a future
  target-tree contract. No private prerequisite-statement protocol is added.
- The cached sources do not include the complete frontend/KLIB/linker setup,
  backend context construction, AST declarations/printer internals, call
  translation helpers, or all lowering/runtime implementations. Direct reuse
  has not been compiled or demonstrated here.
- Kotlin semantic support still needs explicit tests for the accepted subset:
  effectful receiver/argument order, mutable captures and aliases, default
  evaluation, short-circuit/branch values, shadowing, numeric edge cases, nulls,
  and exception behavior. Official JS output is a reference, not a replacement
  for the required JVM/ETS oracle; division by zero and broader Long/float
  behavior were not established by the recorded JS experiment.
- Typed target nodes require independent printer tests and target legality
  validation. Producing a `JsExpression` or a `.d.ts` file proves neither ArkTS
  acceptance nor native ArkUI Builder/slot correctness.
- UI migration must exercise normal source-to-public-CLI output, source-linked
  rejection, and shared-lowering use in both language and UI modes. A successful
  mechanical type change alone does not prove preserved evaluation semantics.
- UI features, fixture behavior, device work, and native builds remain frozen
  for this architecture task. No page repair, full JS runtime adoption, JS-text
  intermediary, duplicate UI language emitter, or new generic compatibility
  claim is authorized by this reference document.

[P]: https://github.com/JetBrains/kotlin/blob/v2.1.20/compiler/ir/backend.js/src/org/jetbrains/kotlin/ir/backend/js/JsLoweringPhases.kt
[P-order]: https://github.com/JetBrains/kotlin/blob/v2.1.20/compiler/ir/backend.js/src/org/jetbrains/kotlin/ir/backend/js/JsLoweringPhases.kt#L744
[O]: https://github.com/JetBrains/kotlin/blob/v2.1.20/compiler/ir/backend.js/src/org/jetbrains/kotlin/ir/backend/js/optimizations.kt
[M]: https://github.com/JetBrains/kotlin/blob/v2.1.20/compiler/ir/backend.js/src/org/jetbrains/kotlin/ir/backend/js/transformers/irToJs/IrModuleToJsTransformer.kt
[M-module]: https://github.com/JetBrains/kotlin/blob/v2.1.20/compiler/ir/backend.js/src/org/jetbrains/kotlin/ir/backend/js/transformers/irToJs/IrModuleToJsTransformer.kt#L190
[M-fragments]: https://github.com/JetBrains/kotlin/blob/v2.1.20/compiler/ir/backend.js/src/org/jetbrains/kotlin/ir/backend/js/transformers/irToJs/IrModuleToJsTransformer.kt#L404
[M-output]: https://github.com/JetBrains/kotlin/blob/v2.1.20/compiler/ir/backend.js/src/org/jetbrains/kotlin/ir/backend/js/transformers/irToJs/IrModuleToJsTransformer.kt#L635
[F]: https://github.com/JetBrains/kotlin/blob/v2.1.20/compiler/ir/backend.js/src/org/jetbrains/kotlin/ir/backend/js/transformers/irToJs/IrFunctionToJsTransformer.kt
[E]: https://github.com/JetBrains/kotlin/blob/v2.1.20/compiler/ir/backend.js/src/org/jetbrains/kotlin/ir/backend/js/transformers/irToJs/IrElementToJsExpressionTransformer.kt
[E-expressions]: https://github.com/JetBrains/kotlin/blob/v2.1.20/compiler/ir/backend.js/src/org/jetbrains/kotlin/ir/backend/js/transformers/irToJs/IrElementToJsExpressionTransformer.kt#L111
[S]: https://github.com/JetBrains/kotlin/blob/v2.1.20/compiler/ir/backend.js/src/org/jetbrains/kotlin/ir/backend/js/transformers/irToJs/IrElementToJsStatementTransformer.kt
[S-statements]: https://github.com/JetBrains/kotlin/blob/v2.1.20/compiler/ir/backend.js/src/org/jetbrains/kotlin/ir/backend/js/transformers/irToJs/IrElementToJsStatementTransformer.kt#L31
[C]: https://github.com/JetBrains/kotlin/blob/v2.1.20/compiler/ir/backend.js/src/org/jetbrains/kotlin/ir/backend/js/transformers/irToJs/JsClassGenerator.kt
[D]: https://github.com/JetBrains/kotlin/blob/v2.1.20/compiler/ir/backend.js/src/org/jetbrains/kotlin/ir/backend/js/lower/JsDefaultArgumentStubGenerator.kt
[D-defaults]: https://github.com/JetBrains/kotlin/blob/v2.1.20/compiler/ir/backend.js/src/org/jetbrains/kotlin/ir/backend/js/lower/JsDefaultArgumentStubGenerator.kt#L33
[N]: https://github.com/JetBrains/kotlin/blob/v2.1.20/compiler/ir/backend.js/src/org/jetbrains/kotlin/ir/backend/js/lower/calls/NumberOperatorCallsTransformer.kt
[N-numbers]: https://github.com/JetBrains/kotlin/blob/v2.1.20/compiler/ir/backend.js/src/org/jetbrains/kotlin/ir/backend/js/lower/calls/NumberOperatorCallsTransformer.kt#L140
