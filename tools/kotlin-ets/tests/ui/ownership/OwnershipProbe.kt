@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import java.io.File
import org.jetbrains.kotlin.ir.declarations.IrSimpleFunction
import org.jetbrains.kotlin.ir.util.dump
import org.jetbrains.kotlin.ir.util.hasAnnotation
import org.jetbrains.kotlin.name.FqName

fun main(args: Array<String>) {
    val sources = args.drop(2)
    val program = withKotlinModule(listOf("-no-stdlib", "-no-reflect", "-classpath", args[0]) + sources) { module ->
        File(args[1], "actual.ir").writeText(module.dump())
        val sink = DiagnosticSink()
        val backend = EtsBackend(sink, listOf(StandardLibraryRules()))
        backend.validateSource(module)
        val program = ComposeLowering(backend.language, sink).lower(module, "ownership.OwnershipPage")
        EtsValidator().validate(program, perFileNames = true)
        val component = program.files.flatMap { it.declarations }.filterIsInstance<EtsClass>().single { it.component }
        check(component.source.file == sources.single { it.endsWith("/Screen.kt") })
        val globals = program.files.flatMap { it.declarations }.filterIsInstance<EtsFunction>().filter { it.builder }
        check(globals.map { it.name }.toSet() == setOf("PrivateCaption", "Leaf", "Chain", "Action", "Frame")) {
            "Expected independent source builders in original source files, got ${globals.map { it.name }}"
        }
        val sourceBuilders = module.files.flatMap { it.declarations }.filterIsInstance<IrSimpleFunction>()
            .filter { it.hasAnnotation(FqName("androidx.compose.runtime.Composable")) }
        val methods = component.members.filterIsInstance<EtsFunction>().filter { it.builder }
        val sourceTargets = (globals + methods).associateBy { it.symbol.id }
        for (source in sourceBuilders) {
            val span = SourceSpan(sourceFile(source)!!.fileEntry.name, source.startOffset, source.endOffset)
            val id = etsFunctionSymbol(source.name.asString(), emptyList(), EtsTypes.VOID, span).id
            val target = sourceTargets.getValue(id)
            check(target.source == span)
            check(target.parameters.map { it.symbol.name } == source.valueParameters.map { it.name.asString() })
            if (target in globals) {
                check(target.kind == EtsFunctionKind.FUNCTION)
                check(program.files.single { it.sourcePath == span.file }.declarations.contains(target))
            } else check(target.kind == EtsFunctionKind.METHOD)
        }
        check(globals.single { it.name == "PrivateCaption" }.exported.not())
        check(methods.map { it.name }.containsAll(listOf("OwnershipPage", "Bridged", "Dependent", "DeepDependent")))
        val nodes = mutableListOf<EtsNode>()
        program.files.forEach { file -> file.declarations.forEach { walkEts(it, nodes::add) } }
        val references = nodes.filterIsInstance<EtsReference>()
        globals.forEach { function ->
            check(references.any { it.symbol == function.symbol && !it.symbol.external })
            walkEts(function) { check(it !is EtsReference || it.symbol.name != "this") }
        }
        val sourceIds = sourceTargets.keys
        nodes.filterIsInstance<EtsMember>().filter { it.symbolId in sourceIds }.forEach {
            check(it.symbolId in methods.map { method -> method.symbol.id })
        }
        val action = globals.single { it.name == "Action" }
        val actionNodes = mutableListOf<EtsNode>()
        walkEts(action, actionNodes::add)
        check(actionNodes.filterIsInstance<EtsReference>().any { it.symbol == action.parameters[1].symbol })
        val actionCall = nodes.filterIsInstance<EtsCall>().first { (it.callee as? EtsReference)?.symbol == action.symbol }
        val callback = actionCall.arguments[1] as EtsLambda
        val captures = mutableListOf<EtsNode>()
        walkEts(callback, captures::add)
        check(captures.filterIsInstance<EtsAssignment>().any { (it.target as? EtsMember)?.name == "count" })
        check(captures.filterIsInstance<EtsReference>().any { it.symbol.name == "this" })
        File(args[1], "ownership.txt").writeText(sourceTargets.values.joinToString("\n") {
            "${it.symbol.id} -> ${if (it in globals) "global" else "page"}; ${it.parameters.map { p -> p.symbol.name }}"
        })
        val helperFiles = program.files.map { file -> file.copy(declarations = file.declarations.filter {
            it is EtsFunction && !it.builder || it is EtsClass && !it.component
        }) }
        File(args[1], "helpers.ts").writeText(EtsPrinter().program(EtsProgram(helperFiles)))
        println("PASS actual IR: five source globals, root/transitive/generated page ownership, exact source symbols/parameters/private visibility and callback captures")
        program
    }
    EtsValidator().validate(program, perFileNames = true)
    File(args[1], "OwnershipPage.ets").writeText(emitEtsProgram(program, ComposeRuntime(StandardLibraryRuntime)))
    val modules = File(args[1], "modules").apply { mkdirs() }
    emitEtsModules(program, ComposeRuntime(StandardLibraryRuntime)).forEach { (name, text) ->
        File(modules, name).writeText(text)
    }
    println("PASS detached typed ownership; emitted complete untouched SDK candidate")
}
