@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.tests.stdlib

import dev.ets.*
import org.jetbrains.kotlin.cli.common.CommonCompilerPerformanceManager
import org.jetbrains.kotlin.cli.common.arguments.*
import org.jetbrains.kotlin.cli.common.messages.*
import org.jetbrains.kotlin.cli.pipeline.ArgumentsPipelineArtifact
import org.jetbrains.kotlin.cli.pipeline.jvm.*
import org.jetbrains.kotlin.com.intellij.openapi.util.Disposer
import org.jetbrains.kotlin.config.Services
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.*
import org.jetbrains.kotlin.ir.util.*
import org.jetbrains.kotlin.ir.visitors.*

fun main(args: Array<String>) {
    val disposable = Disposer.newDisposable()
    val messages = GroupingMessageCollector(PrintingMessageCollector(System.err, MessageRenderer.PLAIN_FULL_PATHS, false), false, false)
    try {
        val options = K2JVMCompilerArguments()
        parseCommandLineArguments(listOf(args[0], "-no-stdlib", "-no-reflect", "-classpath", args[1]), options)
        val input = ArgumentsPipelineArtifact(options, Services.EMPTY, disposable, messages,
            object : CommonCompilerPerformanceManager("loop-adapter-symbols") {})
        val config = checkNotNull(JvmConfigurationPipelinePhase.executePhase(input))
        val analyzed = checkNotNull(JvmFrontendPipelinePhase.executePhase(config))
        val artifact = checkNotNull(JvmFir2IrPipelinePhase.executePhase(analyzed))
        check(!artifact.diagnosticCollector.hasErrors && !messages.hasErrors())
        lowerForLoops(artifact)
        val expected = setOf("kotlin.internal.ProgressionUtilKt.getProgressionLastElement",
            "kotlin.internal.ir.illegalArgumentException")
        val calls = mutableListOf<IrCall>()
        artifact.result.irModuleFragment.acceptVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) { element.acceptChildrenVoid(this) }
            override fun visitCall(expression: IrCall) {
                if (symbolName(expression.symbol.owner) in expected) calls.add(expression)
                expression.acceptChildrenVoid(this)
            }
        })
        check(calls.map { symbolName(it.symbol.owner) }.toSet() == expected)
        val rules = StandardLibraryRules()
        var mutations = 0
        for (call in calls) {
            val owner = call.symbol.owner
            val language = AdapterLanguage(args[0])
            println("ACTUAL ${symbolName(owner)} ${owner.render()}")
            val lowered = checkNotNull(rules.lower(call, language, Scope())) { "Missing loop adapter: ${symbolName(owner)}" }
            check(lowered is EtsCall && lowered.source == language.source(call))
            check(lowered.type == language.type(call.type))
            check(language.inputs.size == call.valueArgumentsCount)
            EtsValidator().validate(EtsProgram(listOf(EtsFile(args[0], listOf(EtsFunction("probe",
                language.inputs.map(::EtsParameter), lowered.type, listOf(EtsReturn(lowered, lowered.source)), lowered.source))))))
            fun reject(label: String, change: () -> Unit, restore: () -> Unit) {
                try {
                    change()
                    val probe = AdapterLanguage(args[0])
                    check(rules.lower(call, probe, Scope()) == null) { "Accepted malformed $label" }
                    check(probe.inputs.isEmpty())
                    mutations++
                } finally { restore() }
            }
            val first = checkNotNull(call.getValueArgument(0))
            val originalType = first.type
            val wrongType = if (originalType.isInt()) calls.first { it.type.isNothing() }.getValueArgument(0)!!.type
                else calls.first { it.type.isInt() }.type
            val resultType = call.type
            val declaredResult = owner.returnType
            val declaredParameter = owner.valueParameters[0].type
            reject("dispatch", { call.insertDispatchReceiver(first) }, { call.removeDispatchReceiver() })
            reject("extension", { call.insertExtensionReceiver(first) }, { call.removeExtensionReceiver() })
            reject("missing argument", { call.putValueArgument(0, null) }, { call.putValueArgument(0, first) })
            reject("argument type", { first.type = wrongType }, { first.type = originalType })
            reject("result type", { call.type = wrongType }, { call.type = resultType })
            reject("declaration result", { owner.returnType = wrongType }, { owner.returnType = declaredResult })
            reject("declaration parameter", { owner.valueParameters[0].type = wrongType },
                { owner.valueParameters[0].type = declaredParameter })
        }
        check(calls.size == 4 && mutations == 28)
        println("PASS: ${calls.size} actual official loop calls; $mutations malformed signatures/dispatches rejected")
    } finally { messages.flush(); Disposer.dispose(disposable) }
}

private class AdapterLanguage(private val file: String) : Language {
    val inputs = mutableListOf<EtsSymbol>()
    override fun source(element: IrElement) = SourceSpan(file, element.startOffset, element.endOffset)
    override fun type(type: IrType): EtsType = when {
        type.isInt() -> EtsTypes.NUMBER
        type.isString() -> EtsTypes.STRING
        type.isNothing() -> EtsTypes.NEVER
        else -> error("Unexpected loop adapter type: ${type.render()}")
    }
    override fun expression(expression: IrExpression, scope: Scope): EtsExpression {
        val symbol = EtsSymbol("input${inputs.size}", "input${inputs.size}", type(expression.type), source(expression))
        inputs.add(symbol)
        return EtsReference(symbol)
    }
    override fun statements(body: IrBody, scope: Scope): List<EtsStatement> = error("Unexpected statements")
    override fun function(function: IrSimpleFunction, scope: Scope): EtsFunction = error("Unexpected function")
    override fun clazz(declaration: IrClass): EtsClass = error("Unexpected class")
}
