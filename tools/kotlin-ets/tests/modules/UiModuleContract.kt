package dev.ets

import java.io.File

fun main(arguments: Array<String>) {
    val program = uiModuleFixture()
    val seen = mutableListOf<EtsProgram>()
    val runtime = EtsRuntimeSupport { part -> seen += part; StandardLibraryRuntime.declarations(part) }
    val modules = emitEtsModules(program, runtime)
    check(modules.keys.toList() == listOf("CaptionCard.ets", "CaptionEvents.ets", "CaptionLogic.ets", "QuietCard.ets", "TextModel.ets"))
    check(seen.size == 5 && seen.all { it.files.size == 1 })
    val card = modules.getValue("CaptionCard.ets")
    check("@Component\nexport struct CaptionCard" in card)
    check("@Builder\n  Caption(model: TextModel = new TextModel())" in card)
    check("@State model: TextModel = new TextModel();" in card)
    check("this.Caption(this.model)" in card)
    check("recordSelection(model);" in card && "formatCaption(item)" in card)
    check("if (true)" in card && "else {" in card && "ForEach(" in card)
    val imports = listOf("import { recordSelection } from \"./CaptionEvents\";",
        "import { formatCaption } from \"./CaptionLogic\";", "import { TextModel } from \"./TextModel\";")
    imports.forEach { expected -> check(card.lines().count { it == expected } == 1) }
    check(modules.getValue("QuietCard.ets").contains("@Builder\n  Caption()"))
    check(modules.getValue("QuietCard.ets").lines().none { "from \"./" in it })
    check(card.lines().count { it.startsWith("function __etsIntDiv(") } == 1)
    check("function __etsSubstring" !in card)
    check("function __etsIntDiv" !in modules.getValue("CaptionLogic.ets"))
    for (name in listOf("__etsSubstring", "__etsSubstringFrom")) {
        check(modules.getValue("CaptionLogic.ets").lines().count { it.startsWith("function $name(") } == 1)
    }
    for (name in listOf("QuietCard.ets", "TextModel.ets", "CaptionEvents.ets")) check("function __ets" !in modules.getValue(name))
    check(modules.values.all { "import hilog from \"@ohos.hilog\";" in it })
    check(seen.all { part -> part.imports.containsAll(program.imports) }) { "Runtime provider lost explicit module imports" }
    check(seen.single { it.files.single().sourcePath == "CaptionCard.kt" }.imports.contains(
        EtsImport("./CaptionLogic", "formatCaption"))) { "Runtime provider lost assembled source imports" }
    check(emitEtsModules(program.copy(files = program.files.reversed()), StandardLibraryRuntime) == modules)

    val quietFile = program.files.single { it.sourcePath == "QuietCard.kt" }
    val quiet = quietFile.declarations.single() as EtsClass
    val typeUseSource = SourceSpan("ComponentTypeUse.kt", 1, 2)
    val typeUse = EtsFunction("acceptComponent", listOf(EtsParameter(EtsSymbol("component:parameter", "component",
        quiet.symbol.type, typeUseSource))), EtsTypes.VOID, emptyList(), typeUseSource)
    val componentTypes = emitEtsModules(EtsProgram(listOf(quietFile,
        EtsFile("ComponentTypeUse.kt", listOf(typeUse)))), StandardLibraryRuntime)
    check("import { QuietCard } from \"./QuietCard\";" in componentTypes.getValue("ComponentTypeUse.ets"))
    check("acceptComponent(component: QuietCard)" in componentTypes.getValue("ComponentTypeUse.ets"))

    fun rejects(value: EtsProgram, message: String, sourceFile: String) {
        seen.clear()
        val failure = runCatching { emitEtsModules(value, runtime) }.exceptionOrNull()
        check(failure is InvalidTarget && message in failure.message.orEmpty()) { "Expected $message; got $failure" }
        check(failure.source.file == sourceFile)
        check(seen.isEmpty()) { "Invalid module plan reached runtime selection" }
    }
    val hiddenEvent = program.copy(files = program.files.map { file ->
        if (file.sourcePath != "CaptionEvents.kt") file else file.copy(declarations = file.declarations.map {
            (it as EtsFunction).copy(exported = false)
        })
    })
    rejects(hiddenEvent, "not exported", "CaptionCard.kt")
    val at = SourceSpan("TypeOnlyCard.kt", 5, 10)
    val model = program.files.first().declarations.single() as EtsClass
    val signature = EtsClass("TypeOnlyCard", listOf(EtsFunction("Caption", listOf(EtsParameter(
        EtsSymbol("parameter:typeOnly", "model", model.symbol.type, at))), EtsTypes.VOID, emptyList(), at,
        kind = EtsFunctionKind.METHOD, builder = true)), at, component = true)
    rejects(EtsProgram(listOf(EtsFile("TextModel.kt", listOf(model.copy(exported = false))),
        EtsFile("TypeOnlyCard.kt", listOf(signature)))), "not exported", "TypeOnlyCard.kt")

    val logic = program.files.single { it.sourcePath == "CaptionLogic.kt" }.declarations.single() as EtsFunction
    val local = logic.copy(name = "formatCaption", source = SourceSpan("CaptionCard.kt", 100, 110))
    rejects(program.copy(files = program.files.map { file ->
        if (file.sourcePath == "CaptionCard.kt") file.copy(declarations = file.declarations + local) else file
    }), "Conflicting module binding", "CaptionCard.kt")

    // External identities must not be rebound to a source function with the same ID.
    val source = SourceSpan("ExternalOwner.kt", 1, 2)
    val owned = EtsFunction("externalCaption", emptyList(), EtsTypes.VOID, emptyList(), source)
    val useSource = SourceSpan("ExternalCard.kt", 3, 4)
    val external = EtsClass("ExternalCard", listOf(EtsFunction("build", emptyList(), EtsTypes.VOID,
        listOf(EtsUiElement(EtsCall(EtsReference(owned.symbol.copy(external = true), useSource), emptyList(),
            EtsTypes.VOID, useSource))), useSource, kind = EtsFunctionKind.METHOD, build = true)),
        useSource, component = true)
    val externalFiles = emitEtsModules(EtsProgram(listOf(EtsFile("ExternalOwner.kt", listOf(owned)),
        EtsFile("ExternalCard.kt", listOf(external)))), EtsRuntimeSupport { emptyList() })
    check("import { externalCaption }" !in externalFiles.getValue("ExternalCard.ets"))

    val heritageModules = uiModuleHeritageContract()
    if (arguments.isNotEmpty()) {
        val output = File(arguments.single())
        check(!output.exists()) { "Fixture output already exists: $output" }
        check(output.mkdirs())
        (modules + heritageModules).forEach { (name, content) -> File(output, name).writeText(content) }
    }
    println("PASS typed UI module names, nested value/type imports, explicit/runtime dependencies, identity negatives and preflight")
}
