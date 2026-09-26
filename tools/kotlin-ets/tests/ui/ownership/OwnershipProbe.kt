@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import dev.ets.pipeline.ComposeWidgetPipeline
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
        val program = ComposeWidgetPipeline(backend, StandardLibraryRuntime)
            .lower(module, "ownership.OwnershipPage")
        EtsValidator().validate(program, perFileNames = true)
        val component = program.files.flatMap { it.declarations }.filterIsInstance<EtsClass>().single { it.component }
        check(component.source.file == sources.single { it.endsWith("/Screen.kt") })
        val globals = program.files.flatMap { it.declarations }.filterIsInstance<EtsFunction>().filter { it.builder }
        val namedGlobals = globals.filterNot { it.name.endsWith("_content") }
        check(namedGlobals.map { it.name }.toSet() == setOf("PrivateCaption", "Leaf", "Chain", "Action", "Frame",
            "Bridged", "Dependent", "DeepDependent")) {
            "Expected source builders in original source files, got ${globals.map { it.name }}"
        }
        check(globals.map { it.name }.containsAll(listOf("Bridged_content", "OwnershipPage_content")))
        val sourceBuilders = module.files.flatMap { it.declarations }.filterIsInstance<IrSimpleFunction>()
            .filter { it.hasAnnotation(FqName("androidx.compose.runtime.Composable")) }
        val sourceTargets = namedGlobals.associateBy { it.symbol.id }
        for (source in sourceBuilders.filter { it.name.asString() != "OwnershipPage" }) {
            val span = SourceSpan(sourceFile(source)!!.fileEntry.name, source.startOffset, source.endOffset)
            val id = etsFunctionSymbol(source.name.asString(), emptyList(), EtsTypes.VOID, span).id
            val target = sourceTargets.getValue(id)
            check(target.source == span)
            check(target.parameters.map { it.symbol.name } == source.valueParameters.map { it.name.asString() })
            check(target.kind == EtsFunctionKind.FUNCTION)
            check(program.files.single { it.sourcePath == span.file }.declarations.contains(target))
        }
        check(globals.single { it.name == "PrivateCaption" }.exported.not())
        check(component.members.filterIsInstance<EtsFunction>().single { it.build }.name == "build")
        val nodes = mutableListOf<EtsNode>()
        program.files.forEach { file -> file.declarations.forEach { walkEts(it, nodes::add) } }
        val references = nodes.filterIsInstance<EtsReference>()
        globals.forEach { function ->
            check(references.any { it.symbol.id == function.symbol.id }) {
                "Unreferenced source or slot builder: ${function.name}"
            }
            walkEts(function) { check(it !is EtsReference || it.symbol.name != "this") }
        }
        val sourceIds = sourceTargets.keys
        nodes.filterIsInstance<EtsMember>().filter { it.symbolId in sourceIds }.forEach {
            error("Top-level source builder was emitted as a component member: ${it.name}")
        }
        val action = globals.single { it.name == "Action" }
        val actionNodes = mutableListOf<EtsNode>()
        walkEts(action, actionNodes::add)
        check(actionNodes.filterIsInstance<EtsReference>().any { it.symbol == action.parameters[1].symbol })
        val actionCall = nodes.filterIsInstance<EtsCall>().first { (it.callee as? EtsReference)?.symbol == action.symbol }
        val callback = actionCall.arguments[1] as EtsLambda
        val captures = mutableListOf<EtsNode>()
        walkEts(callback, captures::add)
        check(captures.any { it is EtsAssignment })
        File(args[1], "ownership.txt").writeText(sourceTargets.values.joinToString("\n") {
            "${it.symbol.id} -> global; ${it.parameters.map { p -> p.symbol.name }}"
        })
        println("PASS actual IR: source builders preserve declarations, visibility and explicit callback captures")
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
