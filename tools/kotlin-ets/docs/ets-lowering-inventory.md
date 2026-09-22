# ETS IR-to-IR lowering inventory

This is the architecture-convergence inventory for Kotlin 2.1.20 post-frontend
lowerings on the ETS backend. It classifies what already runs, what is reused
from official common/JS sources, and what must stay ETS-owned. Behavior is
unchanged by this document.

Pinned references:

- Kotlin/JS 2.1.20 `JsLoweringPhases.kt` (`getJsLowerings`, lines 744-877) as
  recorded in [kotlin-js-backend-reference.md](kotlin-js-backend-reference.md).
- Current production hook: `withKotlinFrontend` in `src/core/Frontend.kt`
  invokes `EtsLoweringPhases.run` after JVM FIR2IR. Implementations remain in
  `src/core/*` and are not a second IR.

Official Kotlin Backend IR (`IrModuleFragment` / `IrClass` / `IrCall` / …)
stays the IR. There is no `KotlinEtsIr`. `EtsProgram` stays the target AST.

```text
Kotlin source → K2/FIR → Kotlin Backend IR
  → EtsLoweringPhases (IR→IR)
  → ETS-ready Kotlin IR
  → IrToEts
  → EtsProgram → Validator → Printer
```

## Classification keys

| Key | Meaning |
| --- | --- |
| `COMMON_REUSE` | Official common pass used with its documented contract; ETS does not replace the algorithm. |
| `COMMON_WITH_TARGET_CONTEXT` | Official common pass, but it requires a `CommonBackendContext` / `LoweringContext` and ETS currently supplies that through the JVM adapter `createJvmLoweringContext`. |
| `JVM_SPECIFIC` | JVM codegen, JVM origin, JVM runtime cell, or `GenerationState` / `JvmBackendContext` implementation detail. Not an ETS semantic pass. |
| `ETS_CUSTOM` | ETS-owned IR rewrite or target-representation adapter. Not an official JS/JVM pipeline phase. |
| `UNKNOWN_NEEDS_PROOF` | Attractive official/JS name whose ETS compatibility is not proven. Do not enable. |

Do not run the full JVM lowering pipeline. Do not run `getJsLowerings()`.
Do not treat `kotlin-stdlib-js` as an ETS stdlib.

## Authoritative phase order

`EtsLoweringPhases.order` is the testable sequence. It matches the production
hook previously inlined in `Frontend.kt` at `arch/kotlin-ets-v2` (`7d9749f`):

1. `SOURCE_INLINE`
2. `LOCAL_DECLARATIONS` (shared variables, local lifting/popup, inner classes, nested extraction)
3. `INHERITED_DEFAULTS`
4. `NATIVE_CONSTRUCTOR_DISPATCH`
5. `SECONDARY_CONSTRUCTORS`
6. `FOR_LOOPS`
7. `STRING_CONCATENATION`
8. `EXPECTED_NULLABILITY`
9. `GENERIC_BOUNDS`
10. `REBIND_INLINED_CAPTURES`

Frontend owns compiler lifetime, FIR, FIR2IR, dependency resolution, and the
single call into this pipeline. It does not own phase order.

## Inventory

### 1. Source-function inline

| Field | Value |
| --- | --- |
| Implementation | `src/core/LibraryInlining.kt` (`lowerSourceInlineFunctions`) |
| Official pass | `CommonInlineCallableReferenceToLambdaPhase`, `FunctionInlining`, `ReturnableBlockTransformer`, `KlibSyntheticAccessorGenerator` |
| BackendContext | `JvmBackendContext` via `createJvmLoweringContext` (`COMMON_WITH_TARGET_CONTEXT`) |
| JVM-specific origin/runtime? | Accessor generation uses the Klib generator, not JVM `Ref`. `produceOuterThisFields = false`. Private cross-file accessors are ETS-named through `NameTable`. Omitted default slots are reassigned because ETS has not run full default-argument lowering. |
| JS corresponding phase | JS inlining / callable-reference-to-lambda prefix in `getJsLowerings` (see reference lines 413-427 for local-declaration prerequisites; inlining is earlier in the same list). |
| ETS reuse? | Yes, bodies only from `FunctionBodies` (source or bounded serialized JVM inline). Missing bodies are recorded, not invented. |
| Prerequisites | Live FIR2IR module; `FunctionBodies` that reject unbound/external/non-inline-binary. |
| Phase-order dependency | Must run before local/inner capture lowering so inlined bodies are present for capture analysis. `REBIND_INLINED_CAPTURES` must run after all IR mutation. |
| Class | `COMMON_WITH_TARGET_CONTEXT` |

### 2. Shared variables

| Field | Value |
| --- | --- |
| Implementation | `src/core/LocalDeclarations.kt` (`SharedVariablesLowering` + `SourceCellManager`) |
| Official pass | `org.jetbrains.kotlin.backend.common.lower.SharedVariablesLowering` |
| BackendContext | Official pass takes `LoweringContext`; ETS overrides `sharedVariablesManager`. Context object is still a JVM-backed `JvmBackendContext` (`COMMON_WITH_TARGET_CONTEXT`). The cell class is ETS (`ETS_CUSTOM`). |
| JVM-specific origin/runtime? | No JVM `Ref` / `ObjectRef`. Cells use `ETS_SHARED_VARIABLE_CELL` origin and a typed `__etsSharedCellN` class. Uninitialized captured variables fail closed. |
| JS corresponding phase | JS shared-variable handling before local declarations (`JsLoweringPhases` local-declaration prerequisites, lines 413-427). JS cells are not imported. |
| ETS reuse? | Capture *discovery* is official. Representation is ETS. |
| Prerequisites | Source inline. Only bodies with named locals or local classes are rewritten; ordinary closures keep native ETS capture. |
| Phase-order dependency | Before `LocalDeclarationsLowering`. Nested inside `LOCAL_DECLARATIONS`. |
| Class | `COMMON_WITH_TARGET_CONTEXT` + `ETS_CUSTOM` (cell) |

### 3. Local declarations

| Field | Value |
| --- | --- |
| Implementation | `src/core/LocalDeclarations.kt` (`LocalDeclarationsLowering`, `LocalClassPopupLowering`) |
| Official pass | `LocalDeclarationsLowering` (`remapTypesInExtractedLocalFunctions = true`), `LocalClassPopupLowering` |
| BackendContext | `JvmBackendContext` (`COMMON_WITH_TARGET_CONTEXT`) |
| JVM-specific origin/runtime? | Visibility policy keeps constructor visibility (not JVM-private rewriting). Residual nested functions fail closed (`arkts-no-nested-funcs`). Local class captured type parameters fail closed. |
| JS corresponding phase | JS local-declaration lowering after shared variables (lines 413-427). |
| ETS reuse? | Yes for lifting, capture parameters, recursion, type substitution. |
| Prerequisites | Shared variables. Source inline. |
| Phase-order dependency | Before inherited defaults, constructor dispatch, and inner constructor consumption. Nested inside `LOCAL_DECLARATIONS`. |
| Class | `COMMON_WITH_TARGET_CONTEXT` |

### 4. Inner classes

| Field | Value |
| --- | --- |
| Implementation | `src/core/LocalDeclarations.kt` (`InnerClassesLowering`, `InnerClassesMemberBodyLowering`, `InnerClassConstructorCallsLowering`) plus ETS `extractNested` / DFS heritage order |
| Official pass | The three common inner-class passes |
| BackendContext | `JvmBackendContext.innerClassesSupport` (`COMMON_WITH_TARGET_CONTEXT`) |
| JVM-specific origin/runtime? | Production *consumes* `JvmLoweredDeclarationOrigin.FIELD_FOR_OUTER_THIS` as an identity token on the generated outer parameter (`LocalDeclarations.kt` identity check). That origin is JVM-named, not a JVM runtime. Migration: record the same binding with an ETS origin. Nested class extraction to the source file mirrors JS static placement (`ETS_CUSTOM`). |
| JS corresponding phase | Inner/local family in the JS local-declaration prefix; JS then keeps file-level classes. |
| ETS reuse? | Official outer-this field/parameter/call rewrite. ETS owns file placement, heritage topological order, and `SourceInnerClassBinding`. |
| Prerequisites | Named top-level outer class; no generic inner binders; Any-only inner heritage; source constructors. Capture lowering first. |
| Phase-order dependency | Nested inside `LOCAL_DECLARATIONS`. Constructor dispatch/secondary constructors read `sourceInnerClassBinding`. |
| Class | `COMMON_WITH_TARGET_CONTEXT` + `ETS_CUSTOM` (placement) + residual `JVM_SPECIFIC` origin token |

### 5. Inherited default arguments

| Field | Value |
| --- | --- |
| Implementation | `src/core/DefaultArguments.kt` (`lowerInheritedDefaults`) |
| Official pass | `MaskedDefaultArgumentFunctionFactory`, `DefaultArgumentStubGenerator`, `DefaultParameterInjector`, `createStaticFunctionWithReceivers`, `moveBodyTo` |
| BackendContext | `CommonBackendContext` delegated from `JvmBackendContext` (`COMMON_WITH_TARGET_CONTEXT`) |
| JVM-specific origin/runtime? | Not JVM bytecode default-stubs. ETS keeps immutable locals in `selectArgumentOrDefault` (JVM stubs mutate parameters). Ordinary non-inherited function defaults stay on `EtsParameter.defaultValue` and are **not** expanded here. JS `getVoid()` / prototype / super-context ABI is not used. |
| JS corresponding phase | JS default-argument generation, override patching, injection (lines 502-527 / 503-521). `JsDefaultArgumentStubGenerator` is **not** reused. |
| ETS reuse? | Common masked dispatch for inherited methods and file-init providers only. |
| Prerequisites | Source inline and local/inner capture lowering, so default lambdas see bound captures/outer links. |
| Phase-order dependency | After `LOCAL_DECLARATIONS`. Before constructor dispatch (constructors have a separate default family). |
| Class | `COMMON_WITH_TARGET_CONTEXT` |

See [inherited-defaults.md](inherited-defaults.md). Expanding this pass onto ordinary
functions would replace a green ETS-direct path; do not do that in this batch.

### 6. Native constructor dispatch

| Field | Value |
| --- | --- |
| Implementation | `src/core/ConstructorDispatch.kt` (`lowerNativeConstructorDispatch`) |
| Official pass | Composes common `DefaultArgumentStubGenerator` / `DefaultParameterInjector` (constructor providers), `InitializersLowering`, `InitializersCleanupLowering`, `FunctionInlining`, `ReturnableBlockTransformer` |
| BackendContext | `CommonBackendContext` delegated from `JvmBackendContext` |
| JVM-specific origin/runtime? | No JVM `<init>` ABI. Synthetic origin `ETS_CONSTRUCTOR_DISPATCH`. Consumes official capture-field origins from local/inner lowering, including the JVM-named outer-this parameter origin as an identity check. |
| JS corresponding phase | Related to JS secondary-constructor/factory conversion (lines 594-601) but **not** that pass. JS factories assume JS class evaluation. |
| ETS reuse? | Official initializer move/cleanup and inlining of initialize helpers. Dispatch selector, nullable unused slots, and `new_*` factories are `ETS_CUSTOM`. |
| Prerequisites | Local/inner capture bindings. Rejects local/inner owners without those bindings. |
| Phase-order dependency | After `INHERITED_DEFAULTS`. Before `SECONDARY_CONSTRUCTORS` (native roots must exist first). |
| Class | `ETS_CUSTOM` composing `COMMON_WITH_TARGET_CONTEXT` pieces |

See [native-constructor-flow.md](native-constructor-flow.md), [constructors.md](constructors.md).

### 7. Secondary constructors

| Field | Value |
| --- | --- |
| Implementation | `src/core/Constructors.kt` (`lowerSecondaryConstructors`) |
| Official pass | No JS/JVM secondary-constructor phase is invoked. Uses official IR utilities: `createStaticFunctionWithReceivers`, `moveBodyTo`, `ValueRemapper`, `DeclarationIrBuilder`. |
| BackendContext | `JvmBackendContext` only for `irFactory` / built-ins (`COMMON_WITH_TARGET_CONTEXT` as a service host, not as a JVM phase). |
| JVM-specific origin/runtime? | Origin `ETS_SECONDARY_CONSTRUCTOR`. Keeps one native allocating root (source primary or unique super-delegating secondary). |
| JS corresponding phase | JS secondary-constructor and factory conversion (lines 594-601) is the reference *shape*, not the implementation. JS factory injection is not run. |
| ETS reuse? | Utilities only. Algorithm is ETS. |
| Prerequisites | Constructor dispatch has already normalized multi-root families. Leading `this` delegation; no abstract/sealed secondary factories; no super-secondary delegation that would allocate a base instance. |
| Phase-order dependency | After `NATIVE_CONSTRUCTOR_DISPATCH`. |
| Class | `ETS_CUSTOM` |

### 8. For loops

| Field | Value |
| --- | --- |
| Implementation | `src/core/ForLoops.kt` (`lowerForLoops`) |
| Official pass | `org.jetbrains.kotlin.backend.common.lower.loops.ForLoopsLowering` |
| BackendContext | `CommonBackendContext` delegated from `JvmBackendContext` with `preferJavaLikeCounterLoop = false` |
| JVM-specific origin/runtime? | Explicitly disables JVM/HotSpot counter-loop shape (`JavaLikeCounterLoopBuilder`). Post-pass ETS type substitution only on *new* calls (`ETS_CUSTOM`). |
| JS corresponding phase | Common for-loop lowering in the JS prefix (same common class). |
| ETS reuse? | Range/progression analysis, induction, empty-range, overflow-safe last element, break/continue retargeting. |
| Prerequisites | Local declarations (loop bodies may contain lifted locals). Stdlib still owns iterator/step runtime calls. |
| Phase-order dependency | After constructor family; before string concat (independent semantically, locked to the historical order). |
| Class | `COMMON_WITH_TARGET_CONTEXT` + `ETS_CUSTOM` (generic call types) |

See [loops.md](loops.md).

### 9. String concatenation

| Field | Value |
| --- | --- |
| Implementation | `src/core/OfficialLowerings.kt` (`lowerStringConcatenations`) |
| Official pass | `org.jetbrains.kotlin.backend.common.lower.FlattenStringConcatenationLowering` |
| BackendContext | `JvmBackendContext` via `createJvmLoweringContext` |
| JVM-specific origin/runtime? | Context construction uses `GenerationState` / `FirJvmBackendClassResolver` / `JvmIrDeserializerImpl` (`JVM_SPECIFIC` adapter). The pass itself is common: String `plus` → `IrStringConcatenation` / constants. No bytecode is emitted. |
| JS corresponding phase | Common flatten-string-concatenation in the JS/native prefix. |
| ETS reuse? | Yes. Operand legality remains a target diagnostic. |
| Prerequisites | Live compiler project. |
| Phase-order dependency | After loops in the locked order. Idempotent on IR that already has no String `plus`. |
| Class | `COMMON_WITH_TARGET_CONTEXT` (pass) hosted by `JVM_SPECIFIC` adapter |

See [official-lowering.md](official-lowering.md).

### 10. Expected nullability

| Field | Value |
| --- | --- |
| Implementation | `src/core/ExpectedNullability.kt` (`lowerExpectedNullability`) |
| Official pass | `AbstractValueUsageTransformer` (common visitor). Not a JS lowering phase. |
| BackendContext | None. Uses `irBuiltIns` from the FIR2IR artifact. |
| JVM-specific origin/runtime? | No. Char→Any boxing is *rejected later* by language lowering; this pass only inserts implicit casts for FIR-omitted nullability-only uses and Char/Any documentation of the gap. Property references are left untouched so the existing diagnostic remains. |
| JS corresponding phase | None. JS type-operator lowering (lines 572-584) is a different, broader pass and is **not** run (`UNKNOWN_NEEDS_PROOF` / JS-specific). |
| ETS reuse? | Visitor skeleton only. |
| Prerequisites | Calls/types from earlier phases should already exist so uses see substituted types. |
| Phase-order dependency | After concat. Before generic bounds. |
| Class | `ETS_CUSTOM` |

See [expected-nullability.md](expected-nullability.md).

### 11. Generic bounds

| Field | Value |
| --- | --- |
| Implementation | `src/core/GenericBounds.kt` (`lowerGenericBounds`) |
| Official pass | Conjunction collapse uses `IrTypeSystemContextImpl.isSubtypeOf`. Named helpers use `IrFakeOverrideBuilder` for class-kind constraints. Not a JS phase. |
| BackendContext | None. |
| JVM-specific origin/runtime? | Origin `ETS_BOUND_CONSTRAINT`. Helpers are source-file interfaces/abstract classes. |
| JS corresponding phase | None. JS does not emit this ETS named-bound encoding. |
| ETS reuse? | Type-system queries and fake-override builder only. |
| Prerequisites | Declaration set after previous synthetic helpers (defaults/ctors/cells) so `NameTable` reserved names include them. |
| Phase-order dependency | Last IR rewrite before capture rebind. |
| Class | `ETS_CUSTOM` |

See [generic-heritage.md](generic-heritage.md).

### 12. Rebind inlined captures

| Field | Value |
| --- | --- |
| Implementation | `src/core/CallCaptures.kt` (`CallCaptures.rebindInlined`) invoked as `KotlinFrontendSession.rebindInlinedCaptures` |
| Official pass | None. Restores FIR argument-capture facts after IR mutation. |
| BackendContext | None. |
| JVM-specific origin/runtime? | No. FIR session is the JVM K2 frontend, which is the production frontend adapter, not a lowering. |
| JS corresponding phase | None. |
| ETS reuse? | ETS-only. |
| Prerequisites | All IR-to-IR phases that can wrap/replace `IrCall` identities. |
| Phase-order dependency | Always last. |
| Class | `ETS_CUSTOM` |

## Infrastructure, not a phase

### JVM lowering-context adapter

| Field | Value |
| --- | --- |
| Implementation | `src/core/OfficialLowerings.kt` (`createJvmLoweringContext`) |
| Class | `JVM_SPECIFIC` |
| What it is | FIR-backed `GenerationState` + `JvmBackendContext` copied from `JvmIrCodegenFactory.invokeLowerings` setup, without running JVM lowerings or codegen. |
| Why it still exists | Official common passes in 2.1.20 take `CommonBackendContext` / `LoweringContext`; the installed compiler's concrete host on this frontend is `JvmBackendContext`. |
| Migration off `JvmBackendContext` onto `EtsBackendContext` | See [Migration](#migration-off-jvmbackendcontext). `src/lower/EtsBackendContext.kt` is the named owner; it does not yet implement `CommonBackendContext`. |

### Binary / KLIB bodies

| Field | Value |
| --- | --- |
| Implementation | `src/core/BinaryBodies.kt` |
| Class | `JVM_SPECIFIC` loader (serialized JVM inline IR only) |
| Not a lowering | Signature JARs are not bodies. KLIB loading is a separate proof, not production CLI. |

## JS / JVM phases deliberately not run

These names appear in `getJsLowerings` / JVM codegen. Enabling any of them
requires a new inventory row with proof. Current class: `UNKNOWN_NEEDS_PROOF`
unless marked `JVM_SPECIFIC`.

| Phase / family | Why it stays off this backend |
| --- | --- |
| Full `getJsLowerings()` | JS intrinsics, `getVoid()`, export/mangling, ES class generator, coroutines, JS numeric `jsImul` / Int32. |
| Full JVM `invokeLowerings` / codegen | Bytecode, box/unbox, JVM bridges, `GenerationState.factory` output. |
| `PropertiesLowering` | Would erase `IrProperty` containers that ETS prints as properties ([declaration-call-contract.md](declaration-call-contract.md)). |
| JS `JsDefaultArgumentStubGenerator` | `getVoid()`, prototype, super-context. |
| JS `NumberOperatorCallsTransformer` | `jsImul`, `jsBitOr` Int32. Numeric ETS semantics belong in IR lowering *later* or in CallRule today; IrToEts must not invent them. |
| JS type-operator / autoboxing / inline-class / coroutine / continuation | Target runtime and IR shapes not owned by ETS yet. |
| JS block decomposition | Depends on type-operator and suspend lowering (lines 624-638). |
| JS ES5/ES6 `JsClassGenerator` | JS AST, not `EtsClass`. |
| Ordinary-function default IR expansion | Would replace the green `EtsParameter.defaultValue` path. |

## IrToEts boundary (not IR-to-IR)

`src/lower/IrToEts.kt` is the IR→`EtsProgram` seam. It must not perform
high-level Kotlin semantic lowering. Example: `kotlin.Int.div` becoming an ETS
runtime intrinsic belongs in an IR-to-IR phase (future) or today's `CallRule`.
IrToEts only maps already-present `IrCall` nodes through `Language` /
`CallRule.lower`. See [ir-to-ets-split.md](ir-to-ets-split.md).

`LanguageLowering` still mixes leftover semantic guards with target
construction. This batch adds the seam; it does not rewrite that 100KB file.

## Migration off `JvmBackendContext`

Recorded here so the contamination gate can stay strict on `src/lower`,
`src/target`, and `src/output` without pretending the adapter is gone.

Current fact: every `COMMON_WITH_TARGET_CONTEXT` pass calls
`createJvmLoweringContext` in `src/core` (frontend JVM adapter). That adapter
may remain. New layers must not import `org.jetbrains.kotlin.backend.jvm`.

Migration steps, not this batch's behavior change:

1. Grow `EtsBackendContext` into a real `CommonBackendContext` /
   `LoweringContext` that exposes `irBuiltIns`, `irFactory`, `symbolTable`,
   `ir.symbols`, `innerClassesSupport`, and `sharedVariablesManager` from the
   live FIR2IR result **without** `GenerationState` / class-file factory.
2. Prove, with the existing concat IR-evidence checks, that constructing this
   context does not rewrite source IR or emit bytecode.
3. Switch `FlattenStringConcatenationLowering`, `ForLoopsLowering`,
   `FunctionInlining`, local/inner/default generators one pass at a time.
4. Replace the `JvmLoweredDeclarationOrigin.FIELD_FOR_OUTER_THIS` identity
   token with an ETS origin published by the inner-class wrapper.
5. Keep `BinaryBodies` and the K2 JVM frontend pipeline in `src/core`.
   They are the frontend JVM adapter, not the ETS backend.

Until step 3 is proven per pass, `JvmEtsIrLowerings` in `src/lower` may only
delegate to the `src/core` functions that call `createJvmLoweringContext`.
Those functions remain the adapter; `src/lower` must not import JVM backend
types.

## Tests that lock this inventory

- `tests/lowering/pipeline.mjs`: phase order, determinism, source-symbol
  identity, no unbound symbols, idempotent re-run of applicable passes.
- `tests/lowering/jvm-contamination.mjs`: `org.jetbrains.kotlin.backend.jvm`
  is absent from `src/lower`, `src/target`, `src/output`.
- `tests/lowering/ir-to-ets.mjs`: IrToEts delegates the same `IrClass` /
  `IrSimpleFunction` instances to `Language`; String `plus` is already gone
  before this seam; declaration names survive.
- Existing language / inline / loops / inheritance / target / module suites
  remain the behavior oracles.
