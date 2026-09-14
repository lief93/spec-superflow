@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class, org.jetbrains.kotlin.fir.symbols.SymbolInternals::class)
package dev.ets.variance.fir

import org.jetbrains.kotlin.cli.common.CommonCompilerPerformanceManager
import org.jetbrains.kotlin.cli.common.arguments.K2JVMCompilerArguments
import org.jetbrains.kotlin.cli.common.arguments.parseCommandLineArguments
import org.jetbrains.kotlin.cli.common.messages.*
import org.jetbrains.kotlin.cli.pipeline.ArgumentsPipelineArtifact
import org.jetbrains.kotlin.cli.pipeline.jvm.*
import org.jetbrains.kotlin.com.intellij.openapi.util.Disposer
import org.jetbrains.kotlin.config.Services
import org.jetbrains.kotlin.fir.FirElement
import org.jetbrains.kotlin.fir.expressions.FirFunctionCall
import org.jetbrains.kotlin.fir.references.FirResolvedNamedReference
import org.jetbrains.kotlin.fir.symbols.impl.FirFunctionSymbol
import org.jetbrains.kotlin.fir.types.*
import org.jetbrains.kotlin.fir.visitors.FirVisitorVoid
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.util.render
import org.jetbrains.kotlin.ir.visitors.*

fun main(args: Array<String>) {
    val disposable = Disposer.newDisposable()
    try {
        val options = K2JVMCompilerArguments()
        parseCommandLineArguments(listOf("-no-stdlib", "-no-reflect", "-classpath", args[0]) + args.drop(1), options)
        val messages = GroupingMessageCollector(PrintingMessageCollector(System.err, MessageRenderer.PLAIN_FULL_PATHS, false), false, false)
        val configured = JvmConfigurationPipelinePhase.executePhase(ArgumentsPipelineArtifact(options, Services.EMPTY,
            disposable, messages, object : CommonCompilerPerformanceManager("capture-proof") {}))!!
        val analyzed = JvmFrontendPipelinePhase.executePhase(configured)!!
        check(!analyzed.diagnosticCollector.hasErrors && !messages.hasErrors())
        val calls = mutableListOf<FirFunctionCall>()
        for (output in analyzed.result.outputs) for (file in output.fir) file.accept(object : FirVisitorVoid() {
            override fun visitElement(element: FirElement) { element.acceptChildren(this) }
            override fun visitFunctionCall(functionCall: FirFunctionCall) {
                if (functionCall.typeArguments.any { (it as? FirTypeProjectionWithVariance)?.typeRef?.coneType is ConeCapturedType })
                    calls.add(functionCall)
                functionCall.acceptChildren(this)
            }
        })
        val translated = JvmFir2IrPipelinePhase.executePhase(analyzed)!!
        check(!translated.diagnosticCollector.hasErrors)
        val irCalls = mutableListOf<IrCall>()
        translated.result.irModuleFragment.acceptChildrenVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) { element.acceptChildrenVoid(this) }
            override fun visitCall(expression: IrCall) { irCalls.add(expression); expression.acceptChildrenVoid(this) }
        })
        val fir = calls.single { (it.calleeReference as FirResolvedNamedReference).name.asString() == "getCell" }
        val symbol = (fir.calleeReference as FirResolvedNamedReference).resolvedSymbol as FirFunctionSymbol<*>
        val irSymbol = translated.result.components.declarationStorage.getIrFunctionSymbol(symbol)
        val ir = irCalls.single { it.symbol == irSymbol && it.startOffset == fir.source!!.startOffset && it.endOffset == fir.source!!.endOffset }
        val captured = (fir.typeArguments.single() as FirTypeProjectionWithVariance).typeRef.coneType as ConeCapturedType
        check(captured.lowerType == null && captured.constructor.projection.kind == ProjectionKind.OUT)
        check(ir.getTypeArgument(0)!!.render().endsWith("Value"))
        println("PASS official FIR retains getCell capture; FIR2IR approximates its type argument to ${ir.getTypeArgument(0)!!.render()}")
        println("PASS exact official declaration symbol and call offsets associate the two representations")
    } finally { Disposer.dispose(disposable) }
}
