@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import java.io.File
import org.jetbrains.kotlin.cli.common.CommonCompilerPerformanceManager
import org.jetbrains.kotlin.cli.common.arguments.parseCommandLineArguments
import org.jetbrains.kotlin.cli.common.arguments.K2JVMCompilerArguments
import org.jetbrains.kotlin.cli.common.fir.FirDiagnosticsCompilerResultsReporter
import org.jetbrains.kotlin.cli.common.messages.GroupingMessageCollector
import org.jetbrains.kotlin.cli.common.messages.MessageRenderer
import org.jetbrains.kotlin.cli.common.messages.PrintingMessageCollector
import org.jetbrains.kotlin.cli.pipeline.ArgumentsPipelineArtifact
import org.jetbrains.kotlin.cli.pipeline.jvm.JvmConfigurationPipelinePhase
import org.jetbrains.kotlin.cli.pipeline.jvm.JvmFir2IrPipelinePhase
import org.jetbrains.kotlin.cli.pipeline.jvm.JvmFrontendPipelinePhase
import org.jetbrains.kotlin.com.intellij.openapi.util.Disposer
import org.jetbrains.kotlin.config.Services
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.declarations.IrDeclarationWithName
import org.jetbrains.kotlin.ir.declarations.IrModuleFragment
import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.symbols.IrSymbol
import org.jetbrains.kotlin.ir.util.dump
import org.jetbrains.kotlin.ir.util.fqNameWhenAvailable
import org.jetbrains.kotlin.ir.visitors.IrElementVisitorVoid
import org.jetbrains.kotlin.ir.visitors.acceptChildrenVoid
import org.jetbrains.kotlin.ir.visitors.acceptVoid

private data class NamedSpan(val name: String, val start: Int, val end: Int)

private fun namedSpans(module: IrModuleFragment): List<NamedSpan> {
    val result = mutableListOf<NamedSpan>()
    module.acceptVoid(object : IrElementVisitorVoid {
        override fun visitElement(element: IrElement) {
            if (element is IrDeclarationWithName && !element.name.isSpecial) {
                result.add(NamedSpan(element.name.asString(), element.startOffset, element.endOffset))
            }
            element.acceptChildrenVoid(this)
        }
    })
    return result
}

private fun plusCalls(module: IrModuleFragment): List<IrCall> {
    val result = mutableListOf<IrCall>()
    module.acceptVoid(object : IrElementVisitorVoid {
        override fun visitElement(element: IrElement) {
            if (element is IrCall && element.symbol.owner.fqNameWhenAvailable?.asString() in
                setOf("kotlin.plus", "kotlin.String.plus")) result.add(element)
            element.acceptChildrenVoid(this)
        }
    })
    return result
}

private fun unbound(module: IrModuleFragment): List<String> {
    val result = mutableListOf<String>()
    module.acceptVoid(object : IrElementVisitorVoid {
        override fun visitElement(element: IrElement) {
            element.javaClass.methods.filter { it.parameterCount == 0 && IrSymbol::class.java.isAssignableFrom(it.returnType) }
                .forEach { method ->
                    method.isAccessible = true
                    val symbol = runCatching { method.invoke(element) as? IrSymbol }.getOrNull() ?: return@forEach
                    if (!symbol.isBound) result.add("${element.javaClass.simpleName}.${method.name}")
                }
            element.acceptChildrenVoid(this)
        }
    })
    return result
}

fun main(args: Array<String>) {
    check(EtsLoweringPhases.order == listOf(
        EtsLoweringPhases.Id.SOURCE_INLINE,
        EtsLoweringPhases.Id.LOCAL_DECLARATIONS,
        EtsLoweringPhases.Id.INHERITED_DEFAULTS,
        EtsLoweringPhases.Id.NATIVE_CONSTRUCTOR_DISPATCH,
        EtsLoweringPhases.Id.SECONDARY_CONSTRUCTORS,
        EtsLoweringPhases.Id.FOR_LOOPS,
        EtsLoweringPhases.Id.STRING_CONCATENATION,
        EtsLoweringPhases.Id.EXPECTED_NULLABILITY,
        EtsLoweringPhases.Id.GENERIC_BOUNDS,
        EtsLoweringPhases.Id.REBIND_INLINED_CAPTURES,
    ))
    val fixture = args[0]
    val compilerArgs = listOf(fixture, "-no-stdlib", "-no-reflect", "-classpath", args[1])
    val disposable = Disposer.newDisposable()
    val messages = GroupingMessageCollector(PrintingMessageCollector(System.err, MessageRenderer.PLAIN_FULL_PATHS, false), false, false)
    try {
        val options = K2JVMCompilerArguments()
        parseCommandLineArguments(compilerArgs, options)
        val input = ArgumentsPipelineArtifact(options, Services.EMPTY, disposable, messages,
            object : CommonCompilerPerformanceManager("ets-lowering-pipeline") {})
        val configured = checkNotNull(JvmConfigurationPipelinePhase.executePhase(input))
        val analyzed = checkNotNull(JvmFrontendPipelinePhase.executePhase(configured))
        FirDiagnosticsCompilerResultsReporter.reportToMessageCollector(analyzed.diagnosticCollector, messages, true)
        check(!analyzed.diagnosticCollector.hasErrors && !messages.hasErrors())
        val artifact = checkNotNull(JvmFir2IrPipelinePhase.executePhase(analyzed))
        check(!artifact.diagnosticCollector.hasErrors && !messages.hasErrors())
        val module = artifact.result.irModuleFragment
        val beforeSpans = namedSpans(module)
        val beforeDump = module.dump()
        File(args[2], "pipeline-before.ir").writeText(beforeDump)
        check(plusCalls(module).isNotEmpty())
        check(unbound(module).isEmpty()) { "Unbound symbols before lowering: ${unbound(module)}" }
        val frontend = KotlinFrontendSession(module, BinaryBodies(artifact),
            org.jetbrains.kotlin.ir.types.IrTypeSystemContextImpl(artifact.result.irBuiltIns),
            CallCaptures(analyzed.result, artifact.result))
        val first = EtsLoweringPhases.run(artifact, frontend.bodies, frontend::rebindInlinedCaptures)
        check(first.context.module === module)
        check(plusCalls(module).isEmpty())
        check(unbound(module).isEmpty()) { "Unbound symbols after lowering: ${unbound(module)}" }
        val afterSpans = namedSpans(module)
        check(beforeSpans.all { it in afterSpans }) { "Source declaration names/offsets must survive lowering" }
        val afterDump = module.dump()
        File(args[2], "pipeline-after.ir").writeText(afterDump)
        val secondDump = run {
            lowerStringConcatenations(artifact)
            module.dump()
        }
        check(secondDump == afterDump) { "Re-running string concatenation on already-lowered IR must be a no-op" }
        withKotlinFrontend(compilerArgs) { session ->
            check(plusCalls(session.module).isEmpty())
            check(namedSpans(session.module).filter { span -> beforeSpans.any { it.name == span.name } }.map { it.name }.toSet()
                == beforeSpans.map { it.name }.toSet())
        }
        println("PASS pipeline order=${EtsLoweringPhases.order.joinToString(",")}; source spans=${beforeSpans.size}; no unbound symbols; concat re-run unchanged")
    } finally {
        messages.flush()
        Disposer.dispose(disposable)
    }
}
