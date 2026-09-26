@file:OptIn(org.jetbrains.kotlin.compiler.plugin.ExperimentalCompilerApi::class,
    org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.tests.stdlib

import dev.ets.*
import org.jetbrains.kotlin.cli.common.CommonCompilerPerformanceManager
import org.jetbrains.kotlin.cli.common.arguments.K2JVMCompilerArguments
import org.jetbrains.kotlin.cli.common.arguments.parseCommandLineArguments
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
import org.jetbrains.kotlin.ir.util.isNullable
import org.jetbrains.kotlin.ir.visitors.*

fun main(args: Array<String>) {
    val disposable = Disposer.newDisposable()
    val messages = GroupingMessageCollector(
        PrintingMessageCollector(System.err, MessageRenderer.PLAIN_FULL_PATHS, false), false, false)
    try {
        val arguments = K2JVMCompilerArguments()
        parseCommandLineArguments(args.toList(), arguments)
        val input = ArgumentsPipelineArtifact(arguments, Services.EMPTY, disposable, messages,
            object : CommonCompilerPerformanceManager("quantifier symbol probe") {})
        val config = checkNotNull(JvmConfigurationPipelinePhase.executePhase(input))
        val frontend = checkNotNull(JvmFrontendPipelinePhase.executePhase(config))
        check(!frontend.diagnosticCollector.hasErrors && !messages.hasErrors())
        val ir = checkNotNull(JvmFir2IrPipelinePhase.executePhase(frontend))
        val calls = mutableListOf<Pair<IrCall, IrFile>>()
        ir.result.irModuleFragment.files.forEach { file -> file.acceptVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) { element.acceptChildrenVoid(this) }
            override fun visitCall(expression: IrCall) {
                calls.add(expression to file)
                expression.acceptChildrenVoid(this)
            }
        }) }
        val intType = calls.first { it.first.type.isInt() }.first.type
        val booleanType = calls.first { it.first.type.isBoolean() }.first.type
        val rules = StandardLibraryRules()
        var accepted = 0
        var rejected = 0
        var mutations = 0
        for ((call, file) in calls.filter { it.first.symbol.owner.name.asString() in setOf("any", "all", "none", "count") }) {
            val owner = call.symbol.owner
            val probe = QuantifierLanguage()
            val target = rules.lower(call, probe, Scope())
            println("ACTUAL ${symbolName(owner)} ${owner.render()} body=${owner.body != null}")
            val negative = file.fileEntry.name.endsWith("QuantifierRejected.kt")
            if (negative) {
                check(target == null && probe.inputs.isEmpty()) { "Accepted unsupported ${owner.render()}" }
                rejected++
                continue
            }
            checkNotNull(target) { "Missing resolved quantifier: ${owner.render()}" }
            check(target.type == probe.type(call.type))
            check(probe.inputs == listOf(call.extensionReceiver, call.getValueArgument(0))) { "Child order/count" }
            val invocation = (if (target is EtsUnary) target.operand else target) as EtsCall
            val reference = invocation.callee as EtsReference
            val count = owner.name.asString() == "count"
            check(reference.symbol.id == if (count) "stdlib:__etsListCount" else "stdlib:__etsListAny")
            check(reference.symbol.external && invocation.typeArguments.size == 1)
            val negate = owner.name.asString() in setOf("all", "none")
            check((target is EtsUnary) == negate)
            if (!count) check((invocation.arguments.last() as EtsLiteral).value == (owner.name.asString() != "all"))
            accepted++
            fun reject(label: String, change: () -> Unit, restore: () -> Unit) {
                try {
                    change()
                    val ignored = QuantifierLanguage()
                    check(rules.lower(call, ignored, Scope()) == null) { "Accepted malformed ${owner.name}: $label" }
                    check(ignored.inputs.isEmpty())
                    mutations++
                } finally { restore() }
            }
            val receiver = call.extensionReceiver!!
            val receiverType = receiver.type
            val predicate = call.getValueArgument(0)!!
            val predicateType = predicate.type
            val typeArgument = call.getTypeArgument(0)
            val result = call.type
            val declaredResult = owner.returnType
            val wrongResult = if (result.isBoolean()) intType else booleanType
            val parameter = owner.valueParameters.single()
            val parameterType = parameter.type
            val declaredReceiver = owner.extensionReceiverParameter!!.type
            val origin = owner.origin
            reject("dispatch", { call.insertDispatchReceiver(receiver) }, { call.removeDispatchReceiver() })
            reject("super", { call.superQualifierSymbol = receiverType.classOrNull }, { call.superQualifierSymbol = null })
            reject("missing receiver", { call.extensionReceiver = null }, { call.extensionReceiver = receiver })
            reject("nullable receiver", { receiver.type = receiverType.makeNullable() }, { receiver.type = receiverType })
            reject("wrong receiver", { receiver.type = intType }, { receiver.type = receiverType })
            reject("missing predicate", { call.putValueArgument(0, null) }, { call.putValueArgument(0, predicate) })
            reject("predicate type", { predicate.type = booleanType }, { predicate.type = predicateType })
            reject("nullable predicate", { predicate.type = predicateType.makeNullable() }, { predicate.type = predicateType })
            reject("missing type argument", { call.putTypeArgument(0, null) }, { call.putTypeArgument(0, typeArgument) })
            reject("wrong type argument", { call.putTypeArgument(0, booleanType) }, { call.putTypeArgument(0, typeArgument) })
            reject("call result", { call.type = wrongResult }, { call.type = result })
            reject("declared result", { owner.returnType = wrongResult }, { owner.returnType = declaredResult })
            reject("parameter", { parameter.type = booleanType }, { parameter.type = parameterType })
            reject("declared receiver", { owner.extensionReceiverParameter!!.type = intType },
                { owner.extensionReceiverParameter!!.type = declaredReceiver })
            reject("source origin", { owner.origin = IrDeclarationOrigin.DEFINED }, { owner.origin = origin })
        }
        check(accepted == 7 && rejected == 11 && mutations == 105) { "$accepted accepted, $rejected rejected, $mutations mutations" }
        println("PASS $accepted actual quantifiers, $rejected unsupported overloads/dispatches, $mutations malformed signatures")
    } finally { messages.flush(); Disposer.dispose(disposable) }
}

private class QuantifierLanguage : Language {
    val inputs = mutableListOf<IrExpression>()
    override fun source(element: IrElement) = SourceSpan("quantifier-symbols.kt", element.startOffset, element.endOffset)
    override fun type(type: IrType): EtsType {
        val simple = type as IrSimpleType
        val arguments = simple.arguments.map { (it as IrTypeProjection).type }
        val result = when (simple.classOrNull?.owner?.fqNameWhenAvailable?.asString()) {
            "kotlin.Int" -> EtsTypes.NUMBER
            "kotlin.Boolean" -> EtsTypes.BOOLEAN
            "kotlin.String" -> EtsTypes.STRING
            "kotlin.collections.Iterable", "kotlin.collections.List", "kotlin.collections.MutableList" ->
                EtsNamedType("Array", listOf(type(arguments.single())))
            "kotlin.Function1" -> EtsFunctionType(listOf(type(arguments[0])), type(arguments[1]))
            null -> EtsTypeParameterType(simple.classifier.toString(), (simple.classifier.owner as IrTypeParameter).name.asString())
            else -> error("Unexpected probe type $type")
        }
        return if (type.isNullable()) EtsNullableType(result) else result
    }
    override fun expression(expression: IrExpression, scope: Scope): EtsExpression {
        inputs.add(expression)
        return EtsReference(EtsSymbol("input${inputs.size}", "input${inputs.size}", type(expression.type), source(expression)))
    }
    override fun statements(body: IrBody, scope: Scope): List<EtsStatement> = error("Not a body-lowering test")
    override fun function(function: IrSimpleFunction, scope: Scope,
        semantics: FunctionTargetSemantics): EtsFunction = error("Not a function-lowering test")
    override fun clazz(declaration: IrClass): EtsClass = error("Not a class-lowering test")
}
