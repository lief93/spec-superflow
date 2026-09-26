@file:OptIn(org.jetbrains.kotlin.compiler.plugin.ExperimentalCompilerApi::class,
    org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.tests.genericmodules

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
import org.jetbrains.kotlin.ir.visitors.*
import java.util.IdentityHashMap

fun main(args: Array<String>) {
    val disposable = Disposer.newDisposable()
    val messages = GroupingMessageCollector(
        PrintingMessageCollector(System.err, MessageRenderer.PLAIN_FULL_PATHS, false), false, false)
    try {
        val arguments = K2JVMCompilerArguments()
        parseCommandLineArguments(args.toList(), arguments)
        val input = ArgumentsPipelineArtifact(arguments, Services.EMPTY, disposable, messages,
            object : CommonCompilerPerformanceManager("generic stdlib symbols") {})
        val config = checkNotNull(JvmConfigurationPipelinePhase.executePhase(input))
        val frontend = checkNotNull(JvmFrontendPipelinePhase.executePhase(config))
        check(!frontend.diagnosticCollector.hasErrors && !messages.hasErrors())
        val ir = checkNotNull(JvmFir2IrPipelinePhase.executePhase(frontend))
        val calls = mutableListOf<Pair<IrCall, String>>()
        ir.result.irModuleFragment.files.forEach { file -> file.acceptVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) { element.acceptChildrenVoid(this) }
            override fun visitCall(expression: IrCall) {
                if (expression.symbol.owner.name.asString() in setOf("map", "filter", "filterNot", "iterator", "get", "set")) {
                    calls.add(expression to file.fileEntry.name)
                }
                expression.acceptChildrenVoid(this)
            }
        }) }
        val intType = calls.flatMap { it.first.symbol.owner.valueParameters }.first { it.type.isInt() }.type
        val rules = StandardLibraryRules()
        val leaked = mutableListOf<String>()
        var accepted = 0
        var rejected = 0
        var mutations = 0
        for ((call, file) in calls) {
            val owner = call.symbol.owner
            val language = SymbolLanguage(file)
            val target = rules.lower(call, language, Scope())
            println("ACTUAL ${symbolName(owner)} ${owner.render()} origin=${owner.origin} body=${owner.body != null}")
            if (file.endsWith("GenericRejected.kt")) {
                check(target == null && language.inputs.isEmpty()) { "Accepted unsupported ${owner.render()}" }
                rejected++
                continue
            }
            checkNotNull(target) { "Missing generic adaptation ${owner.render()}" }
            check(target.type == language.type(call.type))
            check(language.inputs.map { it.first } == listOfNotNull(call.dispatchReceiver, call.extensionReceiver) +
                (0 until call.valueArgumentsCount).mapNotNull(call::getValueArgument)) { "Child identity/order/count" }
            val invocation = target as EtsCall
            val reference = invocation.callee as EtsReference
            check(reference.symbol.external && reference.symbol.id == "stdlib:" + reference.symbol.name)
            if (owner.name.asString() == "map") {
                check(invocation.typeArguments == listOf(language.type(call.getTypeArgument(0)!!), language.type(call.getTypeArgument(1)!!)))
                val parameters = invocation.typeArguments.map { it as EtsTypeParameterType }
                check(parameters[0].id != parameters[1].id && parameters.map { it.name } == listOf("T", "R"))
            } else check(invocation.typeArguments.size == 1 && invocation.typeArguments.single() is EtsTypeParameterType)
            val function = EtsFunction("probe", language.inputs.map { EtsParameter(it.second) }, target.type,
                if (target.type == EtsTypes.VOID) listOf(EtsExpressionStatement(target)) else listOf(EtsReturn(target, target.source)),
                target.source, typeParameters = language.parameters.values.sortedBy { it.id })
            val program = EtsProgram(listOf(EtsFile(file, listOf(function))))
            EtsValidator().validate(program)
            val support = StandardLibraryRuntime.declarations(program)
            check(support.count { it.startsWith("function ") } == 1)
            check(support.any { it.startsWith("function ${reference.symbol.name}<") })
            check(support.count { it.startsWith("class ") } == if (owner.name.asString() == "iterator") 1 else 0)
            accepted++
            if (owner.name.asString() != "map") continue

            fun reject(label: String, change: () -> Unit, restore: () -> Unit) {
                try {
                    change()
                    val probe = SymbolLanguage(file)
                    val result = rules.lower(call, probe, Scope())
                    mutations++
                    if (result != null || probe.inputs.isNotEmpty()) leaked.add(label)
                    println("MUTATION $label declined=${result == null} loweredChildren=${probe.inputs.size}")
                } finally { restore() }
            }
            val receiver = call.extensionReceiver!!
            val receiverType = receiver.type
            val transform = call.getValueArgument(0)!!
            val transformType = transform.type
            val inputType = call.getTypeArgument(0)
            val outputType = call.getTypeArgument(1)
            val resultType = call.type
            val declaredResult = owner.returnType
            val parameter = owner.valueParameters.single()
            val parameterType = parameter.type
            val declaredReceiver = owner.extensionReceiverParameter!!.type
            val origin = owner.origin
            reject("dispatch", { call.insertDispatchReceiver(receiver) }, { call.removeDispatchReceiver() })
            reject("super", { call.superQualifierSymbol = receiverType.classOrNull }, { call.superQualifierSymbol = null })
            reject("missing receiver", { call.extensionReceiver = null }, { call.extensionReceiver = receiver })
            reject("nullable receiver", { receiver.type = receiverType.makeNullable() }, { receiver.type = receiverType })
            reject("wrong receiver", { receiver.type = intType }, { receiver.type = receiverType })
            reject("missing transform", { call.putValueArgument(0, null) }, { call.putValueArgument(0, transform) })
            reject("wrong transform", { transform.type = intType }, { transform.type = transformType })
            reject("nullable transform", { transform.type = transformType.makeNullable() }, { transform.type = transformType })
            reject("missing input", { call.putTypeArgument(0, null) }, { call.putTypeArgument(0, inputType) })
            reject("wrong input identity", { call.putTypeArgument(0, outputType) }, { call.putTypeArgument(0, inputType) })
            reject("wrong output identity", { call.putTypeArgument(1, inputType) }, { call.putTypeArgument(1, outputType) })
            reject("missing output", { call.putTypeArgument(1, null) }, { call.putTypeArgument(1, outputType) })
            reject("call result", { call.type = intType }, { call.type = resultType })
            reject("declared result", { owner.returnType = intType }, { owner.returnType = declaredResult })
            reject("declared transform", { parameter.type = intType }, { parameter.type = parameterType })
            reject("declared receiver", { owner.extensionReceiverParameter!!.type = intType },
                { owner.extensionReceiverParameter!!.type = declaredReceiver })
            reject("source origin", { owner.origin = IrDeclarationOrigin.DEFINED }, { owner.origin = origin })
        }
        check(accepted == 8 && rejected == 6 && mutations == 34) { "$accepted accepted, $rejected rejected, $mutations mutations" }
        check(leaked.isEmpty()) { "Malformed actual map signatures accepted: $leaked" }
        println("PASS 8 generic actual APIs, 6 unsupported boundaries, 34 map signature mutations; exact generic runtime identity/closure")
    } finally { messages.flush(); Disposer.dispose(disposable) }
}

// An adapter probe: preserve official identity/types, record child requests, do not fabricate bodies.
private class SymbolLanguage(private val file: String) : Language {
    val parameters = IdentityHashMap<IrTypeParameter, EtsTypeParameter>()
    val inputs = mutableListOf<Pair<IrExpression, EtsSymbol>>()
    override fun source(element: IrElement) = SourceSpan(file, element.startOffset, element.endOffset)
    override fun type(type: IrType): EtsType {
        val simple = type as IrSimpleType
        val owner = simple.classifier.owner
        val result = if (owner is IrTypeParameter) {
            val parameter = parameters.getOrPut(owner) { EtsTypeParameter("probe:${owner.startOffset}:${parameters.size}", owner.name.asString()) }
            EtsTypeParameterType(parameter.id, parameter.name)
        } else {
            val arguments = simple.arguments.map { (it as IrTypeProjection).type }
            when ((owner as IrClass).fqNameWhenAvailable?.asString()) {
                "kotlin.Int" -> EtsTypes.NUMBER
                "kotlin.Boolean" -> EtsTypes.BOOLEAN
                "kotlin.Unit" -> EtsTypes.VOID
                "kotlin.Array", "kotlin.collections.List", "kotlin.collections.MutableList", "kotlin.collections.Iterable" ->
                    EtsNamedType("Array", listOf(type(arguments.single())))
                "kotlin.collections.Iterator" -> EtsNamedType("__etsIterator", listOf(type(arguments.single())),
                    "stdlib:__etsIterator", external = true)
                "kotlin.Function1" -> EtsFunctionType(listOf(type(arguments[0])), type(arguments[1]))
                else -> error("Unexpected probe type $type")
            }
        }
        return if (simple.nullability == SimpleTypeNullability.MARKED_NULLABLE) EtsNullableType(result) else result
    }
    override fun expression(expression: IrExpression, scope: Scope): EtsExpression {
        val name = "input${inputs.size}"
        val symbol = EtsSymbol(name, name, type(expression.type), source(expression))
        inputs.add(expression to symbol)
        return EtsReference(symbol)
    }
    override fun statements(body: IrBody, scope: Scope): List<EtsStatement> = error("Not a body test")
    override fun function(function: IrSimpleFunction, scope: Scope,
        semantics: FunctionTargetSemantics): EtsFunction = error("Not a function test")
    override fun clazz(declaration: IrClass): EtsClass = error("Not a class test")
}
