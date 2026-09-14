# Shared backend contracts

This is the minimum interface baseline for the four development lanes, not a
claim that their pending language or UI features are complete. It reuses the
existing official IR and typed ETS tree; no new JSON or parallel AST is added.
The integration owner controls changes to these contracts and their tests.

## 1. Frontend and dependency bodies

`withKotlinFrontend(arguments) { session -> ... }` owns the compiler environment.
`session.module` is official resolved IR after the currently verified common
passes. `session.bodies: FunctionBodies` resolves an `IrFunctionSymbol`, never a
method-name string, to:

- `FunctionBody.Available`: the actual declaration, linked body and source span.
- `FunctionBody.Unavailable`: an unbound symbol, external declaration,
  declaration outside the source module, or declaration without a body.

The provider exposes source-module bodies and checked serialized JVM inline
bodies through the same interface. A resolved JAR signature alone is unavailable.
The bounded binary path requires actual serialized IR, SourceFile provenance and
linked canonical symbols; see [binary-bodies.md](binary-bodies.md). The official
inliner consumes both paths. Adapters may handle calls without available bodies.

The session and its body resolver reject access after the callback completes.
Compiler objects returned by them are borrowed: callers must not retain them.
This is not a claim that Kotlin's type system prevents retaining an `IrBody`.
Return an independent `EtsProgram`, diagnostics or emitted artifacts instead.
`withKotlinModule` is a convenience callback on this same implementation, not a
second frontend. Only the frontend owner may change official pass order/context.

## 2. Language and adapters

`Language` maps official types, expressions, bodies, functions and classes to
the existing typed target nodes. `Scope` binds official value-symbol identities
to target expressions; it does not resolve by parameter spelling.

Scoped platform rules, registered library rules and Compose control rules all
implement `CallRule`. A single `adaptCall` dispatcher selects and checks the
result according to `CallContext.VALUE`, `STATEMENT` or `UI`:

```kotlin
fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression?
fun lowerStatement(call: IrCall, language: Language, scope: Scope): List<EtsStatement>?
fun lowerUi(call: IrCall, language: Language, scope: Scope): List<EtsStatement>?
```

- `null` declines; an empty statement list is an accepted no-op.
- Value positions consult only `lower`. Its result is checked against the mapped
  Kotlin call result type, including when a supported value is later discarded.
- Discarded calls and implicit Unit coercions consult `lowerStatement`, then
  `lower`, for each candidate. Explicit scoped override first, independent
  `Scope.callRules` next, then registered `Language.callRules` in order,
  then the ordinary resolved-source-call path. A selected rule is not run twice.
- Effects cannot substitute for object-valued initializers or return values.
- UI positions consult only `lowerUi`, which requires an actual Kotlin Unit
  result and returns `CallResult.Ui`. A void-valued expression or statement
  effect cannot silently become UI. `CallResult.Value`, `Statements` and `Ui`
  preserve this distinction through consumption; the target validator still
  checks the produced nodes in their actual placement.
- Explicitly unsupported adaptations throw `Unsupported` with source evidence;
  malformed target nodes fail `EtsValidator`. Neither case silently falls back.
- Runtime calls are typed `EtsCall`/`EtsSymbol` nodes, not arbitrary ETS strings.

UI calls use the same dispatcher as ordinary calls. Layout, text and button
rules live in `ui/ComposeControlRules.kt`; target API construction and signatures
live in `ui/ArkUiCalls.kt`. Source builder/slot calls, UI repeat and Pager register
through the same interface. Arguments and closures reuse `Language`; no rule
parses source expressions or prints ETS text. Unknown platform values decline
instead of blocking later rules merely because of an `androidx.compose` prefix.
Recognized invalid uses, including consuming the effect-only pager launch as a
Job value, still fail closed.

This unifies API dispatch, not all framework semantics into a call renamer.
Remembered declarations, closure capture and ordered Modifier application remain
framework structural lowering used by the registered rules. They are not an
independent frontend, evaluator or target printer. Broader extraction of these
structural responsibilities is separate from this bounded dispatch change.

## 3. Target tree and runtime support

`EtsProgram` remains the compiler-independent contract. Its declarations,
expressions and statements retain types, symbol identities and source spans.
`EtsValidator` and `walkEts` are shared, exhaustive target consumers.

UI controls use `EtsUiElement` and `EtsUiForEach`; conditions use the existing
`EtsIf` or `EtsConditional` according to statement/value context. Component,
builder and state metadata live on declarations. Attributes, callbacks and
record arguments are typed expressions, not source snippets. The validator
rejects UI DSL in ordinary callbacks and checks record fields and iteration item
types before output. `EtsNamedType.external` distinguishes a provider-owned
runtime type from a source declaration with the same name and ID spelling.

`EtsRuntimeSupport.declarations(program)` selects pinned target runtime support
from the typed program. The CLI injects `StandardLibraryRuntime`; output code
does not import standard-library selection policy. The provider owns its symbol
namespace, fixed helper definitions and transitive helper dependencies.

The current provider walks every target branch, default, field and body. Only
external `stdlib:` identities select helpers; matching text or a user-defined
same-name symbol does not. Unknown owned identities fail, transitive helpers are
included once, and order is deterministic. Target signatures remain on the
typed references; no separate name-only adapter result is introduced here.
This is a runtime selection interface, not a binary linker or full DCE engine.

## 4. Output

### R1 inheritance increment (implementation in progress)

The shared target tree now distinguishes `EtsClassKind.CLASS/INTERFACE` and
records `baseClass`, `interfaces` and `abstract` on `EtsClass`. Heritage refers to
existing nonexternal class symbol identities. This increment accepts non-generic
source heritage only, not structural same-name assignability or external class
assumptions. `EtsFunction.abstract` denotes a bodyless signature; `overrides`
records inherited function IDs. `EtsMember.symbolId`, when supplied, is checked
against the receiver's actual declared/inherited member. It is not an alias.

`EtsSuperConstructorCall(baseClass, arguments, source)` is a statement with real
source arguments. A derived constructor requires exactly one direct-base
delegation as its first statement; ordinary callbacks/methods cannot contain it.
The validator checks target inheritance cycles, kind/signature mismatches,
concrete interface fulfillment, inherited member access and subtype assignment.
The printer emits class/interface heritage and signatures, never stub bodies.
The shared traversal visits super arguments; dependency consumers own heritage
type reachability. No Kotlin compiler objects enter these target nodes.

Independent target tests pass for this increment; source-language/SDK/native
integration is pending R1 completion. Do not treat the API as full inheritance
or generic dispatch support.

`emitEtsProgram(program, runtime)` and `emitEtsModules(program, runtime)` validate
before runtime selection/printing. Module output computes imports by declaration
and type identity. `EtsPrinter` only formats target syntax. It must not read
Kotlin IR, run adapters, choose preview branches or infer missing values.

### R2D overload identity increment

`EtsFunction.name` and `EtsSymbol.name` are emitted bindings. Optional
`EtsFunction.sourceName` retains the original spelling when a target collision
requires renaming; `etsFunctionSymbol` accepts the same final optional argument.
Function identity continues to derive from the original source spelling and
source span, not the renamed binding. Existing unrenamed declarations are
unchanged. The target tree receives already-resolved, uniquely named calls;
neither validation nor printing chooses a Kotlin overload.

Language lowering owns one declaration-keyed allocation using the official
Kotlin/JS `NameTable`. It reserves unchanged names first, preserves the first
source-ordered overload spelling and allocates only the conflicting spellings.
Declaration, reference and member construction use that same allocation.
Source list traversal order must not change the result. This is not a stable
binary ABI promise after declarations are added or reordered in the source.

The validator rejects duplicate canonical top-level identities before building
ownership maps and duplicate same-kind method identities within a class.
References must match both the actual identity and emitted spelling/type;
members additionally obey receiver ownership and static/instance rules. Existing
accessor pairs remain distinct kinds. A valid call to another overload with an
identical ETS signature is not a target type error: actual-IR binding evidence
and Kotlin/generated-code result traces must detect incorrect source selection.

Initial scope: overload groups declared in one source file or a nonvirtual final
class, with cross-file consumers. Split-file groups, inherited/virtual overloads,
overloaded constructors and framework-specific overloaded UI calls are not
claimed. Target contract RED d3SQRy (missing API), RED Iifyiw (duplicate identity
accepted), GREEN lyjtCh. Source-language, SDK and native R2D acceptance pending.

The CLI assembles results before publishing files and refuses existing output
paths. `ComposeLowering.lower` now returns `EtsProgram`; `UiTextModule` was removed.
The page CLI uses this same validator/printer with `ComposeRuntime` composing
the standard-library provider. Fixed typography/touch runtime support is selected
by checked typed dependencies. It is not a container for generated page text.

## Ownership and parallel work

| Lane | Owns | Shared boundary |
| --- | --- | --- |
| 1. Official frontend/dependencies | Compiler lifetime, linking/body policy, verified official passes | `KotlinFrontendSession`, `FunctionBodies` |
| 2. Language Lowering | Language semantics and typed target construction | `Language`, `Scope`, target types/symbols |
| 3. Standard library/runtime | Resolved library rules and target runtime behavior | `CallRule`, `EtsRuntimeSupport` |
| 4. ETS representation/output | Target node coverage, validation, imports, syntax and UI target integration | `EtsProgram`, validator/traversal, output functions |

Workers extend their implementations; changes to shared node/result types go
through the integration owner first. Contract tests belong to that shared
boundary. Architectural increments are recorded separately; broad language and
framework coverage is not implied by completing a shared interface.

## Kotlin/JS reference, pinned 2.1.20

The local official source archive is indexed in
`artifacts/kotlin-js-official-prototype-20260913/official-backend/index.json`.
See also [the reference inventory](kotlin-js-backend-reference.md).

- `ir/inline/FunctionInlining.kt`: `InlineFunctionResolver` separates declaration
  selection from the actual common inliner. We reuse that inliner; the ETS body
  availability contract is our facade over checked source and binary body policy.
- `backend/common/serialization/NonLinkingIrInlineFunctionDeserializer.kt`:
  loading serialized bodies is not symbol linking. No JVM signature is treated
  as a KLIB body, and no JS linker is grafted onto JVM symbols.
- `ir/backend/js/transformers/irToJs/IrElementToJsExpressionTransformer.kt` and
  `IrElementToJsStatementTransformer.kt`: expression and statement contexts are
  distinct. We follow that separation with typed ETS nodes, not JS comma/dynamic
  expressions.
- `ir/backend/js/transformers/irToJs/IrModuleToJsTransformer.kt` and `js/dce/Dce.kt`:
  declaration/import identity and reachability precede printing. Our bounded
  runtime dependency closure follows this principle, not the whole JS DCE pass.

## Checks

The completed run and exact evidence paths are recorded in
[shared-contracts-verification.md](shared-contracts-verification.md).

- `node tools/kotlin-ets/tests/language/typed.mjs`: official cross-file body,
  borrowed lifetime, symbols/defaults, adapter precedence, bad value rejection,
  registered/scoped effects, Unit coercion and handled empty effects.
- `bash tools/kotlin-ets/tests/stdlib/check-runtime-tree.sh`: complete target
  traversal, helper closure/identity/order, shared output provider, reject invalid
  target before runtime emission.
- Existing backend, inline, modules and UI suites guard the production consumers;
  JVM/host differential results and SDK builds are separate evidence levels.
- `bash tools/kotlin-ets/tests/ui/target-contract.sh`: independent typed UI tree,
  nested traversal, argument/record/iteration checks and callback DSL rejection.
- `bash tools/kotlin-ets/tests/ui/typed-program.sh`: actual official IR to typed
  UI program with the printer and output module absent from the test classpath.
