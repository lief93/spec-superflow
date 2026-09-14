# Generic Types and Declarations

## Target Contract

```kotlin
data class EtsNamedType(val name: String, val arguments: List<EtsType> = emptyList(),
    val symbolId: String? = null) : EtsType
data class EtsTypeParameter(val id: String, val name: String, val upperBound: EtsType? = null)
data class EtsTypeParameterType(val id: String, val name: String) : EtsType
```

`EtsFunction`, `EtsClass` and `EtsFunctionType` append
`typeParameters: List<EtsTypeParameter> = emptyList()`. All existing positional
constructors remain compatible. A type parameter's identity contains its source
file, owning declaration kind/name/offset and parameter index, not just its spelling. Independent
declarations named `T` therefore cannot substitute for each other.
Officially lifted copies retain source offsets but receive the lifted owner's
identity, preventing an outer parameter from accidentally binding a copied one.

Every source-class `EtsNamedType` has the same `symbolId` as
`etsClassSymbol(name, declarationSource).id`. This includes constructor results,
parameter/result types, fields, `this`, nested generic arguments and object types.
Native target types keep a null `symbolId`. A class value's canonical symbol is
the raw declaration reference; instantiated instance types carry type arguments.
The module lane can resolve source ownership by ID without inferring from names.

Type dependencies include named arguments, nullable/tuple contents, function
parameters/results and each generic declaration's optional `upperBound`.
`EtsTypeParameterType` is a leaf, not a source-module declaration reference.

## Lowering and Substitution

`LanguageLowering` uses actual Kotlin 2.1.20 IR classifiers, type projections,
resolved call type arguments and receiver types. It never parses source text,
clones JVM output, or substitutes printed strings. `T` and explicitly marked
`T?` remain distinct; unsupported projections do not fall back to `Object`.
An explicit Kotlin `Any` type/bound may still map to target `Object`.

`etsSubstitute(type, substitutions)` recursively substitutes by parameter ID.
Nested generic function binders are protected from capture. Nominal class IDs
survive substitution, and nullable substitutions do not produce nested nullable
wrappers. `etsInstantiate(signature, arguments)` opens the callable's own binders
with an exact type-argument count.

Function references keep the original declaration symbol and its generic
signature. `EtsCall.typeArguments` records resolved actual types. Member calls
first substitute the owning class's parameters from the actual receiver, then
instantiate the method's own parameters. Constructors retain concrete class
arguments. Property getter/setter access also substitutes the receiver, while
accessor declarations remain ordinary `EtsFunction` nodes with GETTER/SETTER kinds.

Officially lifted class members with no dispatch receiver use the existing
`EtsFunction.static` field and `EtsMember(EtsReference(classSymbol), ...)` calls.
Their explicit capture parameters and resolved type arguments are not rewritten.
Static members have an independent generic scope: they cannot refer to the
class's original type parameters, but may declare their own copied parameters.
The validator distinguishes class-value and instance member receivers.
Semantically empty lowered container statements are omitted; nonempty blocks
retain their scope, including shadowed local bindings.

Default arguments retain the existing argument list with `EtsUndefined` slots;
declaration defaults are evaluated by the target function. No wrapper, name
specialization or new call form is introduced. Existing external stdlib adapters
may continue carrying pre-instantiated signatures plus printed type arguments.

The validator checks type-parameter binding, class identity and type-argument
counts, upper bounds, generic call arguments/results, instantiated constructor
parameters and receiver-substituted member types. Source-class generic arguments
are invariant. A specialized counterfeit function symbol is still unbound: a
matching printed name is insufficient.

## Bounded Support

Supported: non-reified top-level generic source functions (including recursion and
extensions), simple primary-constructor generic classes, generic methods,
nested class/collection/function types, nullable arguments, defaults and existing
property accessors. Single upper bounds are retained when their types are already
representable, including explicit `T : Any`.

Still rejected: residual local function declarations not removed by the official
phase, local classes, reified parameters, declaration/use-site variance, star
projections, multiple bounds, definitely-not-null intersection types and the
existing unsupported inheritance/overload/suspend cases. Member dispatch through
a bounded type parameter rather than the concrete owning class is not supported.
Lexically shadowing a different generic parameter with the same printed name is
rejected instead of silently renaming it or losing its identity. This is not a
complete Kotlin generic type checker, inheritance engine or module validator.

### SDK Local-Function Boundary

The initial local-generic fixture passed Node execution and target-tree checks but
failed actual SDK compilation with `arkts-no-nested-funcs`, at line 41 of the
generated Functions module. The integration evidence is retained at
`/private/tmp/kotlin-ets-modules-sdk-Sitncv/sdk-assemble.stderr`.
This invalidates the earlier claim of local-generic support.

`LanguageLowering` still rejects an `IrSimpleFunction` in statement position with a
source-linked `UNSUPPORTED` diagnostic, before publishing output. `EtsValidator`
also rejects nested `EtsFunction` statements, including inside lambdas. Ordinary
Kotlin lambdas and class methods/accessors remain supported. `LocalGeneric.kt`
now retains `locally/keep` as a positive public-CLI/JVM regression, alongside
captured outer generic types and a generic-class-owned lifted method.

The installed SDK's `typescript.js` also defines `arkts-no-generic-lambdas`
(`cookBookTag[49]`, line 155581); replacing the declaration with a generic arrow
is not a certified solution. `tests/generics/sdk/GenericArrow.ets` is an unverified
static candidate probe only, not a positive fixture or support claim.

The core lane now directly runs official Kotlin 2.1.20
[`SharedVariablesLowering`](https://github.com/JetBrains/kotlin/blob/v2.1.20/compiler/ir/backend.common/src/org/jetbrains/kotlin/backend/common/lower/SharedVariablesLowering.kt)
and [`LocalDeclarationsLowering`](https://github.com/JetBrains/kotlin/blob/v2.1.20/compiler/ir/backend.common/src/org/jetbrains/kotlin/backend/common/lower/LocalDeclarationsLowering.kt).
The latter owns capture parameters, copied/remapped generic parameters, rewritten
call/return symbols and declaration placement; see `createLiftedDeclaration`,
`createNewParameters`, `fillArguments` and `insertLoweredDeclarationForLocalFunction`.
The language/target lane consumes these ordinary IR declarations, not a duplicate
lifting or capture-conversion implementation. Core's shared-variable manager
adapts cells to a typed source-owned generic class instead of JVM `Ref` or JS
dynamic intrinsics. Backend's reserved-name guard exempts only exact
`ETS_SHARED_VARIABLE_CELL` origin identity; user `__ets` declarations remain errors.
Captured variables without initializers and unsupported function-reference forms
remain fail-closed. Integration-owned local-function/SDK evidence is recorded
separately; host execution alone is not SDK certification.

## Verification

```sh
node tools/kotlin-ets/tests/generics/run.mjs
node tools/kotlin-ets/tests/generics/typed.mjs
```

The first test compiles the same `Functions.kt`/`Classes.kt`/`LocalGeneric.kt` inputs on JVM and via
the public language CLI, executes generated ETS through the cached TypeScript
runtime, and compares twelve grouped results. It also asserts preserved names,
default-call shape, accessor nodes, absence of nested functions/generic arrows,
and rejection/no artifact for three unsupported
inputs. Positive cases include nested generic classes, recursion, lambdas,
receiver substitutions, nullable generic storage and property mutation.

The second test lowers genuine official compiler IR and inspects the typed tree.
It verifies distinct identities, unspecialized function bindings, actual type
arguments, member/constructor substitutions and defaults, then rejects malformed
target cases with specific expected failure reasons, including residual nested
functions and unremapped class type parameters in static methods. Evidence and command logs
are retained in the announced `tests/generics/.work` directories.

SDK compilation and multi-file assembly are run by the integration owner, using
these same public fixtures. This lane does not run SDK/device operations or
independent review. Node type erasure and target validation do not replace that
SDK gate.
