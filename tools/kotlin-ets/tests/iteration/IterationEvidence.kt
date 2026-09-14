@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import java.io.File
import org.jetbrains.kotlin.backend.common.lower.loops.ForLoopsLowering
import org.jetbrains.kotlin.cli.common.CommonCompilerPerformanceManager
import org.jetbrains.kotlin.cli.common.arguments.*
import org.jetbrains.kotlin.cli.common.messages.*
import org.jetbrains.kotlin.cli.pipeline.ArgumentsPipelineArtifact
import org.jetbrains.kotlin.cli.pipeline.jvm.*
import org.jetbrains.kotlin.com.intellij.openapi.util.Disposer
import org.jetbrains.kotlin.config.KotlinCompilerVersion
import org.jetbrains.kotlin.config.Services
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.*
import org.jetbrains.kotlin.ir.util.*
import org.jetbrains.kotlin.ir.visitors.*

private fun nodes(root: IrElement): List<IrElement> {
    val result = mutableListOf<IrElement>()
    root.acceptVoid(object : IrElementVisitorVoid {
        override fun visitElement(element: IrElement) {
            result.add(element)
            element.acceptChildrenVoid(this)
        }
    })
    return result
}

fun main(args: Array<String>) {
    check(KotlinCompilerVersion.VERSION == "2.1.20")
    val phase = ForLoopsLowering::class.java
    println("Official phase: ${phase.name}; loadedFrom=${phase.protectionDomain.codeSource.location}")
    val disposable = Disposer.newDisposable()
    val messages = GroupingMessageCollector(PrintingMessageCollector(System.err, MessageRenderer.PLAIN_FULL_PATHS, false), false, false)
    try {
        val options = K2JVMCompilerArguments()
        parseCommandLineArguments(listOf(args[0], "-no-stdlib", "-no-reflect", "-classpath", args[1]), options)
        val input = ArgumentsPipelineArtifact(options, Services.EMPTY, disposable, messages,
            object : CommonCompilerPerformanceManager("official-iteration-evidence") {})
        val config = checkNotNull(JvmConfigurationPipelinePhase.executePhase(input))
        val analyzed = checkNotNull(JvmFrontendPipelinePhase.executePhase(config))
        val artifact = checkNotNull(JvmFir2IrPipelinePhase.executePhase(analyzed))
        check(!artifact.diagnosticCollector.hasErrors && !messages.hasErrors())
        val module = artifact.result.irModuleFragment
        lowerLocalDeclarations(artifact)
        val before = nodes(module)
        val originalCalls = before.filterIsInstance<IrCall>().associateWith { it.type }
        val iterators = before.filterIsInstance<IrVariable>().filter { it.origin == IrDeclarationOrigin.FOR_LOOP_ITERATOR }
        val original = before.filterIsInstance<IrVariable>().filter { it.origin == IrDeclarationOrigin.FOR_LOOP_VARIABLE }
            .associateWith { Triple(it.symbol, it.name, it.startOffset) }
        val jumps = before.filterIsInstance<IrBreakContinue>()
        val lambdas = before.filterIsInstance<IrFunctionExpression>()
        val functions = before.filterIsInstance<IrSimpleFunction>().associateWith { it.name to it.valueParameters.map { p -> p.name } }
        File(args[2], "before.ir").writeText(module.dump())
        lowerForLoops(artifact)
        val after = nodes(module)
        File(args[2], "after.ir").writeText(module.dump())
        val calls = after.filterIsInstance<IrCall>()
        check(originalCalls.all { (call, type) -> call.type == type }) { "Original call result types must not change" }
        File(args[2], "calls.txt").writeText(calls.map { call ->
            "${symbolName(call.symbol.owner)}: receiver=${(call.dispatchReceiver ?: call.extensionReceiver)?.type?.render()}; " +
                "arguments=${(0 until call.valueArgumentsCount).map { call.getValueArgument(it)?.type?.render() }}; result=${call.type.render()}"
        }.distinct().sorted().joinToString("\n"))
        val retained = after.filterIsInstance<IrVariable>().filter { it.origin == IrDeclarationOrigin.FOR_LOOP_ITERATOR }
        check(retained.isNotEmpty() && retained.size < iterators.size)
        check(retained.all { it.type.classOrNull?.owner?.fqNameWhenAvailable?.asString() in
            setOf("kotlin.collections.Iterator", "kotlin.collections.MutableIterator") })
        for (symbol in listOf("kotlin.Array.get", "kotlin.IntArray.get", "kotlin.ranges.IntProgression.<get-first>",
            "kotlin.ranges.IntProgression.<get-last>", "kotlin.ranges.IntProgression.<get-step>")) {
            check(calls.any { symbolName(it.symbol.owner) == symbol }) { "Missing actual lowered call: $symbol" }
        }
        val arrayReads = after.filterIsInstance<IrTypeOperatorCall>().filter {
            it.operator == IrTypeOperator.IMPLICIT_CAST &&
                (it.argument as? IrCall)?.let { call -> symbolName(call.symbol.owner) == "kotlin.Array.get" } == true
        }
        check(arrayReads.isNotEmpty())
        check(arrayReads.all { cast ->
            val call = cast.argument as IrCall
            call.type == cast.typeOperand && call.startOffset == cast.startOffset && call.endOffset == cast.endOffset
        }) { "Official array reads need instantiated result types, retaining casts and source" }
        check(jumps.all { it.loop in after.filterIsInstance<IrLoop>() })
        check(after.filterIsInstance<IrFunctionExpression>().containsAll(lambdas))
        original.forEach { (declaration, state) ->
            check(declaration in after && Triple(declaration.symbol, declaration.name, declaration.startOffset) == state)
        }
        functions.forEach { (function, names) -> check(function.name == names.first && function.valueParameters.map { it.name } == names.second) }
        println("PASS official IR: iterator variables ${iterators.size}->${retained.size}; retained only collection protocols; " +
            "arrays/progressions use official primitive loops; jumps=${jumps.size}; lambdas=${lambdas.size}; original identities/names/source retained")
        lowerStringConcatenations(artifact)
        val program = EtsBackend(DiagnosticSink(), listOf(StandardLibraryRules())).lower(module)
        val target = mutableListOf<EtsNode>()
        program.files.forEach { file -> file.declarations.forEach { walkEts(it, target::add) } }
        for (name in listOf("__etsIterator", "__etsIntProgression")) {
            val types = target.filterIsInstance<EtsVariable>().map { it.symbol.type }.filterIsInstance<EtsNamedType>().filter { it.name == name }
            check(types.isNotEmpty() && types.all { it.external && it.symbolId == "stdlib:$name" })
        }
        check(program.files.flatMap { it.declarations }.filterIsInstance<EtsClass>().all {
            val type = it.symbol.type as EtsNamedType
            return@all !type.external && type.symbolId == it.symbol.id
        })
        val variables = target.filterIsInstance<EtsVariable>()
        original.keys.forEach { declaration ->
            check(variables.any { !it.mutable && it.symbol.name == declaration.name.asString() &&
                it.source.start == declaration.startOffset && it.source.file == args[0] })
        }
        StandardLibraryRuntime.declarations(program)
        println("PASS typed runtime identities, original immutable iteration bindings, and runtime dependency closure")
    } finally {
        messages.flush()
        Disposer.dispose(disposable)
    }
}
