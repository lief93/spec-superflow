# Source property accessors

The Kotlin frontend already resolves an `IrProperty` into an optional backing
field and getter/setter declarations, with calls linked by
`correspondingPropertySymbol`. The ETS backend consumes those symbols rather
than matching accessor method names or parsing source text.

## Official reference and target-specific work

Kotlin 2.1.20's
[PropertiesLowering](https://github.com/JetBrains/kotlin/blob/v2.1.20/compiler/ir/backend.common/src/org/jetbrains/kotlin/backend/common/lower/PropertiesLowering.kt)
separates fields and accessor declarations. Its JS backend's
[JsPropertyAccessorInlineLowering](https://github.com/JetBrains/kotlin/blob/v2.1.20/compiler/ir/backend.js/src/org/jetbrains/kotlin/ir/backend/js/lower/JsPropertyAccessorInlineLowering.kt)
additionally applies safety rules before replacing accessor calls with direct
storage access.

These implementations are architectural references here, not invoked passes.
ETS retains source properties as `get name()` / `set name(parameter)` and reuses
the existing typed function/body lowering for their implementations. It does not
flatten all accessors into fields or translate a second copy of their logic.

## Mapping

- A stored property with default accessors keeps the existing direct-field form.
- A property with any custom accessor emits its getter and setter, including a
  default counterpart if present, under the original property name.
- A computed property without storage emits no invented field.
- When storage exists for a custom accessor, it is a private
  `__etsField_<property>` field. The namespace is already reserved by the core.
- Resolved property calls access the target property. Explicit `IrGetField` /
  `IrSetField` accesses use the backing field, so `field` does not recursively
  invoke its own accessor.
- Constructor initialization writes storage directly, in source initialization
  order; it does not run the setter.
- Setter parameter names, early returns, branches, calls and mutations go
  through shared language lowering and target type validation.

This adds member accessors for the existing simple-class and object slice.
Delegation, extension properties, inheritance, generic classes and top-level
storage are not made supported by this change. Source semantics that require
those capabilities remain rejected rather than silently replaced with defaults.

## Verification

`node tools/kotlin-ets/tests/language/accessors.mjs` generates ETS with the
public CLI and compares execution against a separately compiled Kotlin/JVM
oracle. It covers eighteen cases including repeated reads, conditional setters,
initialization, receiver evaluation order, compound assignment and post-increment.
The test uses the target AST to check accessor/property and parameter names.

`bash tools/kotlin-ets/tests/target/run.sh` checks accessor syntax and rejects
invalid getter/setter arity and result types. `tests/language/sdk.mjs` includes
the accessor fixture in its actual ETS-module compilation set. Host execution of
the language oracle is not device execution; SDK compilation is a separate check.
