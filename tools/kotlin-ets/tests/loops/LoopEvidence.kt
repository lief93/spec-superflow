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
            object : CommonCompilerPerformanceManager("official-loop-evidence") {})
        val config = checkNotNull(JvmConfigurationPipelinePhase.executePhase(input))
        val analyzed = checkNotNull(JvmFrontendPipelinePhase.executePhase(config))
        val artifact = checkNotNull(JvmFir2IrPipelinePhase.executePhase(analyzed))
        check(!artifact.diagnosticCollector.hasErrors && !messages.hasErrors())
        val module = artifact.result.irModuleFragment
        lowerLocalDeclarations(artifact)
        val before = nodes(module)
        val iterators = before.filterIsInstance<IrVariable>().filter { it.origin == IrDeclarationOrigin.FOR_LOOP_ITERATOR }
        check(iterators.isNotEmpty())
        val variables = before.filterIsInstance<IrVariable>().filter { it.origin == IrDeclarationOrigin.FOR_LOOP_VARIABLE }
            .associateWith { Triple(it.symbol, it.name, it.startOffset) }
        val nativeLoops = before.filterIsInstance<IrLoop>().filter { it.origin != IrStatementOrigin.FOR_LOOP_INNER_WHILE }
        val jumps = before.filterIsInstance<IrBreakContinue>()
        val lambdas = before.filterIsInstance<IrFunctionExpression>()
        File(args[2], "loops-before.ir").writeText(module.dump())
        lowerForLoops(artifact)
        val after = nodes(module)
        File(args[2], "loops-after.ir").writeText(module.dump())
        val calls = after.filterIsInstance<IrCall>()
        File(args[2], "calls.txt").writeText(calls.map {
            "${symbolName(it.symbol.owner)}: ${it.symbol.owner.render()}"
        }.distinct().sorted().joinToString("\n"))
        check(after.filterIsInstance<IrVariable>().none { it.origin == IrDeclarationOrigin.FOR_LOOP_ITERATOR })
        check(after.filterIsInstance<IrLoop>().containsAll(nativeLoops))
        check(after.filterIsInstance<IrFunctionExpression>().containsAll(lambdas))
        val loweredLoops = after.filterIsInstance<IrLoop>().toSet()
        check(jumps.all { it.loop in loweredLoops })
        variables.forEach { (declaration, original) ->
            check(declaration in after && Triple(declaration.symbol, declaration.name, declaration.startOffset) == original)
        }
        check(calls.none { symbolName(it.symbol.owner).endsWith(".iterator") || symbolName(it.symbol.owner).endsWith(".hasNext") })
        println("PASS official IR: iterators=${iterators.size}->0; jumps=${jumps.size}; nativeLoops=${nativeLoops.size}; " +
            "lambdas=${lambdas.size}; original loop binding identity/source preserved")
        lowerStringConcatenations(artifact)
        val program = EtsBackend(DiagnosticSink(), listOf(StandardLibraryRules())).lower(module)
        val targetNodes = mutableListOf<EtsNode>()
        program.files.forEach { file -> file.declarations.forEach { walkEts(it, targetNodes::add) } }
        val loops = targetNodes.filterIsInstance<EtsLoop>()
        check(loops.any { it.doWhile } && loops.any { !it.doWhile })
        val snapshots = loops.flatMap { loop -> loop.body.filterIsInstance<EtsExpressionStatement>() }
            .mapNotNull { it.expression as? EtsAssignment }
            .filter { (it.target as? EtsReference)?.symbol?.name?.startsWith("__etsLoopValue") == true }
        check(snapshots.isNotEmpty())
        check(snapshots.all { assignment ->
            targetNodes.filterIsInstance<EtsVariable>().any { it.symbol == (assignment.value as EtsReference).symbol && !it.mutable }
        })
        println("PASS typed target: immutable condition snapshots=${snapshots.size}; original per-iteration consts retained")
    } finally {
        messages.flush()
        Disposer.dispose(disposable)
    }
}
