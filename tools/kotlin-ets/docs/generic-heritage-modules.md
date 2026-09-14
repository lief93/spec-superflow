# Generic heritage modules

## R2A boundary

This output lane owns `tests/modules/generic-heritage/` and this document.
`Modules.kt` remains unchanged: its existing recursive type collector includes
generic parent arguments, source-class types, constructor calls and member
receiver/signature types. The member declaration ID is not a standalone import.
No output fix has been demonstrated and no alias or name-based fallback is added.

Main owns generic hierarchy validation/substitution. The fixtures use the
existing `EtsClass.typeParameters`, `EtsNamedType.arguments`, `baseClass`,
`interfaces`, `EtsSuperConstructorCall`, `EtsFunction.overrides`, and
`EtsMember.symbolId` contracts. No new target field or public API is requested.
Expected shared behavior is to preserve the original inherited member ID while
substituting its signature through every parent edge by binder ID, including
override checks. Same-spelled `T` binders in separate declarations are distinct.

## Finite typed fixture

The fixture uses synthetic target source spans, not a parsed Kotlin program:

- `Readable.kt`: pure exported `Readable<T>` interface with `read(): T`.
- `Holder.kt`: `Holder<T> implements Readable<T>`, storing its constructor value
  and implementing `read` with the interface's original override identity.
- `Middle.kt`: `Middle<T> extends Holder<T>`, forwarding its explicit value.
- `TextHolder.kt`: concrete `Middle<string>` parent arguments.
- `TokenModel.kt`: source-named model retaining its `text` constructor parameter.
- `ModelHolder.kt`: concrete `Middle<TokenModel>` parent arguments, requiring
  both the parent and source argument-type imports.
- `Consumers.kt`: inherited nongeneric `read` calls through concrete, base,
  interface and parameterized receiver types; `readGeneric<T>` is a top-level
  generic helper, not a generic member method.

The global helper, class and interface all use a binder displayed as `T`, with
different IDs. Parent types and member references carry actual declaration
identities. The constructor/method bodies use the existing lexical class
receiver convention with a non-external source-class type; there is no detached
or ownerless `this`, fake external class type or fabricated global reference.

Tests check source-file objects/spans, declaration and parameter names, original
member IDs with instantiated signatures, concrete and type-parameter parent
syntax, forwarded constructor arguments, exact/deduplicated imports and stable
ordering. They reject imports of members or generic binder names.

Eleven negative cases require `InvalidTarget`, the expected source span, and zero
runtime provider invocations: missing parent arguments; unknown parent ID;
same-spelled unknown binder ID; wrong member ID; wrong instantiated member type;
hidden signature-only interface; hidden source type in a parent argument;
constructor input of a same-named but different source type; colliding source-type
imports; incompatible instantiations of the same ancestor; and a violated parent
type-parameter bound. No overload, nested-class, variance, alias, default-interface
body, library-loading or Compose behavior is expanded.

## Prepared commands

Run only after main's validator is ready and an exclusive build slot is granted:

```sh
node tools/kotlin-ets/tests/modules/generic-heritage/run.mjs
node tools/kotlin-ets/tests/modules/generic-heritage/sdk.mjs <successful-contract-evidence>
```

The contract runner copies exact target/output/runtime/test inputs into a unique
frozen directory before compiling, records SHA256 hashes and uses
`-XX:ActiveProcessorCount=2 -XX:+UseSerialGC`. No frontend or whole-compiler build
is involved. SDK verification refuses inputs that no longer match the snapshot.

The fixed `Index.ets` SDK consumer imports the generated modules and checks the
source signatures through actual SDK compilation, including concrete-to-base,
concrete-to-interface, generic model and numeric argument calls. Generated ETS
bytes are copied unchanged into a fresh existing Harmony seed. Set
`KOTLIN_ETS_SDK_SEED` when a different existing seed is required.

The SDK runner reuses the accepted `ui-sdk-evidence.mjs` verifier without edits.
All seven modules need clean checker entries and matching hashes. The six runtime
modules need `filesInfo.txt` records. The pure `Readable.ets` interface needs
AST-confirmed interface-only content, clean semantic evidence, and SDK dependency
edges; it is not omitted from coverage or forced into runtime by a stub. ABC/HAP,
consumer, verifier and emitted source hashes are recorded.

## Verification evidence

After main's explicit exclusive compiler/SDK slot grant, both scoped runs passed:

- Target: `tests/modules/generic-heritage/.work/contract-NVWD3J/result.json`.
  Seven modules, concrete and parameterized heritage, original inherited member
  identities, names, imports and eleven source-linked negatives passed. All
  live inputs matched the frozen target/output/runtime/test snapshot.
- Actual SDK: `/private/tmp/kotlin-ets-generic-heritage-sdk-w4pIq2/manifest.json`.
  `ohpm-install` and `sdk-assemble` exited zero. Six runtime input records and
  the pure generic `Readable.ets` checked interface dependency cover all seven
  unchanged modules. ABC plus signed/unsigned HAP hashes are recorded.

No production or generated ETS changes were needed. Production hashes are in
both manifests, including `Modules.kt`:
`f597bc89e6d2184a29a3dc06f9d9f2e40bf9163c7ce5de0695c79f65eadd149f`
and main's `Validator.kt`:
`e393cfb4e062a50b95d5bc7a99bb8f206d5cf99945ca356c8b38c787f798a340`.
The exclusive heavy build slot was released immediately after SDK completion.
Main retains whole-round public integration ownership. This is not Kotlin/JVM
differential, ArkVM execution, native interaction or source-level Language/Compose
integration evidence.
