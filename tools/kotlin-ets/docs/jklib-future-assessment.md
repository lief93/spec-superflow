# JKLIB future assessment

Conclusion: **NO_VALUE** for the current Kotlin 2.1.20 ETS production compiler.

Production stays on Kotlin 2.1.20. This spike inspects Kotlin **2.4.0** sources
only. It does not upgrade the compiler, add a JKLIB classpath, or replace the
JVM serialized-IR route.

## What 2.4.0 actually contains

Pinned tree: JetBrains/kotlin tag `v2.4.0`.

| Artifact | Path | Stated purpose |
| --- | --- | --- |
| CLI driver | `compiler/cli/cli-jklib/src/org/jetbrains/kotlin/cli/jklib/K2JKlibCompiler.kt` | "entry-point for compiling Kotlin code into a Klib with references to jars" |
| CLI README | `compiler/cli/cli-jklib/README.md` | "experimental and not intended to be used outside of J2CL" |
| Serialization README | `compiler/ir/serialization.jklib/README.md` | "serializing IR to KLIBs with Java links"; "experimental and not intended to be used outside of J2CL" |
| Linker | `compiler/ir/serialization.jklib/src/org/jetbrains/kotlin/ir/backend/jklib/JKlibIrLinker.kt` | KotlinIrLinker for JVM/klib; Java types become descriptor stubs |
| Serializer | `JKlibModuleSerializer.kt` | Writes IR using `IrSerializationSettings` |
| Tests | `compiler/jklib.tests` | Uses `:compiler:cli-jklib` and `kotlin-stdlib-jklib-for-test` |

`K2JKlibCompiler.compileKlibAndDeserializeIr` is documented as the "Entry point
used by J2CL to get the IR tree." K1 `doExecute` is rejected ("K1 compiler entry
point is no supported.").

## WITH_INLINE_BODIES

There is no `WITH_INLINE_BODIES` flag in the 2.4.0 JKLIB driver or linker.

The related official setting is `IrSerializationSettings.bodiesOnlyForInlines`:

> Whether to serialize bodies of only inline functions. Effectively, this setting
> is only relevant to Kotlin/JVM.

Its default is `publicAbiOnly`. `JKlibKlibSerializationPhase` constructs
`JKlibModuleSerializer(IrSerializationSettings(configuration), ...)` and writes
zip KLIBs with metadata plus serialized IR. The JVM header-KLIB / inline-body
knob is not a bytecode decompiler.

Kotlin 2.4.0 release notes discuss intra-module inlining while producing `.klib`
for **Native / JS / Wasm**, not JVM class-file recovery.

## Java bytecode is not reconstructed as Kotlin IR

`JKlibIrLinker` for a null/Java module uses `MetadataJVMModuleDeserializer`
(`IrModuleDeserializerKind.SYNTHETIC`). Java declarations are wrapped with the
stub generator:

> Wrap java declaration with lazy ir
>
> These classes are created with the stub generator and are already complete.

That is metadata stubs plus Kotlin IR for Kotlin sources compiled into a KLIB
that may *reference* jars. It is not "arbitrary JVM bytecode → full Kotlin IR."

## Why this does not replace the production JVM route

The production compiler is Kotlin **2.1.20**. That tree has no `cli-jklib`,
`serialization.jklib`, or `K2JKlibCompiler`. Adopting JKLIB would require a
compiler upgrade, a J2CL-oriented experimental backend, and a second IR
serialization format beside:

- current JVM `BinaryBodies` / `JvmIrDeserializerImpl` (`-Xserialize-ir=inline`)
- current JS `KlibLoader` / `ModulesStructure` / `loadIr` / `JsIrLinker`

Neither existing route is replaced by JKLIB:

- JS KLIB already loads official linked `IrModuleFragment`s for KLIB inputs.
- JVM serialized IR already loads bounded inline bodies from class files.
- JKLIB's value is J2CL (Kotlin IR + Java *links*), not Harmony ETS.

## Verdict

**NO_VALUE** as a substitute for the production JVM dependency route.

Revisit only if all of the following become true:

1. Production Kotlin is upgraded past 2.1.20 to a release where JKLIB is a
   supported, non-J2CL compiler product.
2. The product serializes **Kotlin** IR bodies we need, with official identity,
   without claiming Java bytecode recovery.
3. A measured gap remains that neither JS KLIB loading nor JVM serialized IR
   covers.

Until then, keep JKLIB isolated from production sources. Do not add
`compiler/cli-jklib` to the 2.1.20 classpath.

## Sources

- [Kotlin 2.4.0 What's New](https://kotlinlang.org/docs/whatsnew24.html)
- [K2JKlibCompiler.kt](https://github.com/JetBrains/kotlin/blob/v2.4.0/compiler/cli/cli-jklib/src/org/jetbrains/kotlin/cli/jklib/K2JKlibCompiler.kt)
- [cli-jklib README](https://github.com/JetBrains/kotlin/blob/v2.4.0/compiler/cli/cli-jklib/README.md)
- [serialization.jklib README](https://github.com/JetBrains/kotlin/blob/v2.4.0/compiler/ir/serialization.jklib/README.md)
- [JKlibIrLinker.kt](https://github.com/JetBrains/kotlin/blob/v2.4.0/compiler/ir/serialization.jklib/src/org/jetbrains/kotlin/ir/backend/jklib/JKlibIrLinker.kt)
- [IrSerializationSettings.kt](https://github.com/JetBrains/kotlin/blob/v2.4.0/compiler/ir/serialization.common/src/org/jetbrains/kotlin/backend/common/serialization/IrSerializationSettings.kt)
