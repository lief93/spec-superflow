package dev.ets

import dev.ets.pipeline.ComposeWidgetPipeline
import java.io.File

fun main(args: Array<String>) {
    val program = withKotlinModule(listOf("-no-stdlib", "-no-reflect", "-classpath", args[0]) + args.drop(2)) { module ->
        val sink = DiagnosticSink()
        val backend = EtsBackend(sink, listOf(StandardLibraryRules()))
        ComposeWidgetPipeline(backend, StandardLibraryRuntime).lower(module, "models.ui.ModelPage")
    }
    EtsValidator().validate(program, perFileNames = true)
    val entry = program.files.flatMap { it.declarations }.filterIsInstance<EtsFunction>()
        .single { it.name == "ModelPage" && it.builder }
    check(entry.parameters.map { it.symbol.name } == listOf("minimum", "extra"))
    val nodes = mutableListOf<EtsNode>()
    program.files.forEach { file -> file.declarations.forEach { walkEts(it, nodes::add) } }
    val texts = nodes.filterIsInstance<EtsUiElement>().filter { (it.call.callee as? EtsReference)?.symbol?.name == "Text" }
    check(texts.size == 4)
    val textCalls = texts.mapNotNull { it.call.arguments.firstOrNull() as? EtsCall }
    check(textCalls.mapNotNull { (it.callee as? EtsReference)?.symbol?.name }.toSet() == setOf("scenario", "selectedLabel"))
    check(textCalls.all { it.type == EtsTypes.STRING })
    check(nodes.any { it is EtsIf })
    val callback = nodes.filterIsInstance<EtsCall>().filter { (it.callee as? EtsReference)?.symbol?.id == "arkui:onClick" }
        .flatMap { it.arguments.filterIsInstance<EtsLambda>() }.single()
    check(callback.source.file!!.endsWith("/ModelPage.kt"))
    var adjustsSelection = false
    walkEts(callback) { if (it is EtsReference && it.symbol.name == "adjustSelection") adjustsSelection = true }
    check(adjustsSelection)
    val output = File(args[1]).apply { mkdirs() }
    emitEtsModules(program, ComposeRuntime(StandardLibraryRuntime)).forEach { (name, text) -> File(output, name).writeText(text) }
    // Replay only the actual typed event body; a host VM cannot render ArkUI.
    val click = EtsFunction("click", callback.parameters, EtsTypes.VOID, callback.body, callback.source, exported = true)
    val helpers = EtsProgram(program.files.map { file -> file.copy(declarations = file.declarations.filter {
        it is EtsGlobal || it is EtsFunction && !it.builder || it is EtsClass && !it.component
    } + if (file.sourcePath == callback.source.file) listOf(click) else emptyList()) })
    EtsValidator().validate(helpers, perFileNames = true)
    val host = File(output, "host").apply { mkdirs() }
    emitEtsModules(helpers, StandardLibraryRuntime).forEach { (name, text) -> File(host, name).writeText(text) }
    println("PASS typed model values reach Text, both branches retained, original parameters and actual callback exported for replay")
}
