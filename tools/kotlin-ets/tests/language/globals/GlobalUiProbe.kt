package dev.ets

import java.io.File

fun main(args: Array<String>) {
    val program = withKotlinModule(listOf("-no-stdlib", "-no-reflect", "-classpath", args[0]) + args.drop(2)) { module ->
        val sink = DiagnosticSink()
        val backend = EtsBackend(sink, listOf(StandardLibraryRules()))
        backend.validateSource(module)
        ComposeLowering(backend.language, sink).lower(module, "globals.ui.GlobalPage")
    }
    EtsValidator().validate(program, perFileNames = true)
    val component = program.files.flatMap { it.declarations }.filterIsInstance<EtsClass>().single { it.component }
    val callbacks = mutableListOf<EtsLambda>()
    walkEts(component) { node ->
        if (node is EtsCall && (node.callee as? EtsReference)?.symbol?.id == "arkui:onClick")
            callbacks += node.arguments.filterIsInstance<EtsLambda>()
    }
    val callback = callbacks.single()
    check(callback.source.file!!.endsWith("/UiState.kt"))
    check(component.source.file!!.endsWith("/UiPage.kt"))
    var writesOwnerStorage = false
    walkEts(callback) { node ->
        if (node is EtsReference && node.symbol.name == "__etsSet_counter") writesOwnerStorage = true
        check(node !is EtsAssignment || (node.target as? EtsReference)?.symbol?.name != "counter")
    }
    check(writesOwnerStorage)
    val output = File(args[1]).apply { mkdirs() }
    emitEtsModules(program, ComposeRuntime(StandardLibraryRuntime)).forEach { (name, text) ->
        File(output, name).writeText(text)
    }
    // Replay the actual lowered event body without pretending a host VM renders ArkUI.
    val click = EtsFunction("click", callback.parameters, EtsTypes.VOID, callback.body, callback.source, exported = true)
    val helpers = EtsProgram(program.files.map { file -> file.copy(declarations =
        file.declarations.filter { it is EtsGlobal || it is EtsFunction && !it.builder } +
            if (file.sourcePath == component.source.file) listOf(click) else emptyList()) })
    EtsValidator().validate(helpers, perFileNames = true)
    val host = File(output, "host").apply { mkdirs() }
    emitEtsModules(helpers, StandardLibraryRuntime).forEach { (name, text) -> File(host, name).writeText(text) }
    println("PASS detached typed Compose slot callback retains owner-file global write")
}
