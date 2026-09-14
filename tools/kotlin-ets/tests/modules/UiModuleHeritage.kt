package dev.ets

fun uiModuleHeritageContract(): Map<String, String> {
    fun origin(file: String) = SourceSpan(file, 1, 2)
    val contract = EtsClass("CaptionContract", emptyList(), origin("CaptionContract.kt"),
        exported = true, kind = EtsClassKind.INTERFACE)
    val baseSource = origin("CaptionBase.kt")
    val value = EtsFunction("value", emptyList(), EtsTypes.NUMBER,
        listOf(EtsReturn(EtsLiteral(7, EtsTypes.NUMBER, baseSource), baseSource)), baseSource,
        kind = EtsFunctionKind.METHOD)
    val base = EtsClass("CaptionBase", listOf(value, EtsFunction("constructor", listOf(EtsParameter(
        EtsSymbol("base:seed", "seed", EtsTypes.NUMBER, baseSource))), EtsTypes.VOID, emptyList(), baseSource,
        kind = EtsFunctionKind.CONSTRUCTOR)), baseSource, exported = true,
        interfaces = listOf(contract.symbol.type as EtsNamedType))
    val seedSource = origin("CaptionSeed.kt")
    val seed = EtsFunction("captionSeed", emptyList(), EtsTypes.NUMBER,
        listOf(EtsReturn(EtsLiteral(7, EtsTypes.NUMBER, seedSource), seedSource)), seedSource, exported = true)
    val derivedSource = origin("DerivedCaption.kt")
    val derived = EtsClass("DerivedCaption", listOf(EtsFunction("constructor", emptyList(), EtsTypes.VOID,
        listOf(EtsSuperConstructorCall(base.symbol.type as EtsNamedType, listOf(EtsCall(
            EtsReference(seed.symbol, derivedSource), emptyList(), EtsTypes.NUMBER, derivedSource)), derivedSource)),
        derivedSource, kind = EtsFunctionKind.CONSTRUCTOR)), derivedSource, exported = true,
        baseClass = base.symbol.type as EtsNamedType)
    val consumerSource = origin("CaptionValue.kt")
    val instance = EtsParameter(EtsSymbol("consumer:caption", "caption", derived.symbol.type, consumerSource))
    val consumer = EtsFunction("captionValue", listOf(instance), EtsTypes.NUMBER, listOf(EtsReturn(
        EtsCall(EtsMember(EtsReference(instance.symbol), value.name, value.symbol.type, consumerSource,
            symbolId = value.symbol.id), emptyList(), EtsTypes.NUMBER, consumerSource), consumerSource)),
        consumerSource, exported = true)
    val program = EtsProgram(listOf(contract, base, seed, derived, consumer).map { declaration ->
        EtsFile(declaration.source.file!!, listOf(declaration))
    })
    val modules = emitEtsModules(program, StandardLibraryRuntime)
    check("import { CaptionContract } from \"./CaptionContract\";" in modules.getValue("CaptionBase.ets"))
    check("import { CaptionBase } from \"./CaptionBase\";" in modules.getValue("DerivedCaption.ets"))
    check("import { captionSeed } from \"./CaptionSeed\";" in modules.getValue("DerivedCaption.ets"))
    check("super(captionSeed());" in modules.getValue("DerivedCaption.ets"))
    check(modules.getValue("CaptionValue.ets").lines().filter { it.startsWith("import ") } ==
        listOf("import { DerivedCaption } from \"./DerivedCaption\";")) { "A member ID became a fabricated top-level import" }
    var runtimeCalls = 0
    val hidden = program.copy(files = program.files.map { file ->
        if (file.sourcePath == "CaptionContract.kt") file.copy(declarations = listOf(contract.copy(exported = false))) else file
    })
    val failure = runCatching { emitEtsModules(hidden, EtsRuntimeSupport { runtimeCalls++; emptyList() }) }.exceptionOrNull()
    check(failure is InvalidTarget && "not exported" in failure.message.orEmpty() && failure.source == baseSource)
    check(runtimeCalls == 0)
    println("PASS heritage imports, super argument traversal, inherited member identity without fabricated imports")
    return modules
}
