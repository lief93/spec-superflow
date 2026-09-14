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
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.types.*
import org.jetbrains.kotlin.ir.util.fqNameWhenAvailable
import org.jetbrains.kotlin.ir.util.isNullable
import org.jetbrains.kotlin.ir.util.render
import org.jetbrains.kotlin.ir.visitors.*

// Inspect actual official pre-backend calls. Runtime equivalence is tested separately.
fun main(args: Array<String>) {
    val expectedRejections = args[0].toInt()
    val disposable = Disposer.newDisposable()
    val messages = GroupingMessageCollector(
        PrintingMessageCollector(System.err, MessageRenderer.PLAIN_FULL_PATHS, false), false, false)
    try {
        val arguments = K2JVMCompilerArguments()
        parseCommandLineArguments(args.drop(1), arguments)
        val input = ArgumentsPipelineArtifact(arguments, Services.EMPTY, disposable, messages,
            object : CommonCompilerPerformanceManager("stdlib symbol probe") {})
        val configuration = checkNotNull(JvmConfigurationPipelinePhase.executePhase(input))
        val frontend = checkNotNull(JvmFrontendPipelinePhase.executePhase(configuration))
        check(!frontend.diagnosticCollector.hasErrors && !messages.hasErrors())
        val ir = checkNotNull(JvmFir2IrPipelinePhase.executePhase(frontend))
        check(!ir.diagnosticCollector.hasErrors && !messages.hasErrors())
        val calls = mutableListOf<Pair<IrCall, String>>()
        ir.result.irModuleFragment.files.forEach { file ->
            file.acceptChildrenVoid(object : IrElementVisitorVoid {
                override fun visitElement(element: IrElement) { element.acceptChildrenVoid(this) }
                override fun visitCall(expression: IrCall) {
                    calls.add(expression to file.fileEntry.name)
                    expression.acceptChildrenVoid(this)
                }
            })
        }
        val intType = calls.first { it.first.type.isInt() }.first.type
        val booleanType = calls.first { it.first.type.isBoolean() }.first.type
        val listTypes = calls.map { it.first.type }.filter {
            it.classOrNull?.owner?.fqNameWhenAvailable?.asString() == "kotlin.collections.List"
        }.distinct()
        val rules = StandardLibraryRules()
        var accepted = 0
        var rejected = 0
        var invalidIrResults = 0
        var invalidTargetResults = 0
        var invalidFilters = 0
        for ((call, file) in calls) {
            val language = RecordingLanguage(file)
            val emitted = rules.lower(call, language, Scope())
            if (emitted == null) {
                rejected++
                check(language.inputs.isEmpty()) { "Rejected call lowered children" }
                println("REJECT " + symbolName(call.symbol.owner))
                continue
            }
            accepted++
            check(emitted.source == language.source(call)) { "Lost call-site source span" }
            check(emitted.type == language.type(call.type)) { "Wrong target result type" }
            language.validate(emitted)
            if (symbolName(call.symbol.owner) in setOf("kotlin.collections.filter", "kotlin.collections.filterNot")) {
                val owner = call.symbol.owner
                println("RESOLVED ${symbolName(owner)} origin=${owner.origin} ${owner.render()}")
                fun rejectMutation(label: String, change: () -> Unit, restore: () -> Unit) {
                    try {
                        change()
                        val probe = RecordingLanguage(file)
                        check(rules.lower(call, probe, Scope()) == null) { "Accepted malformed filter: $label" }
                        check(probe.inputs.isEmpty()) { "Malformed filter lowered children: $label" }
                        invalidFilters++
                    } finally { restore() }
                }
                val receiver = checkNotNull(call.extensionReceiver)
                val receiverType = receiver.type
                val predicate = checkNotNull(call.getValueArgument(0))
                val predicateType = predicate.type
                val typeArgument = call.getTypeArgument(0)
                val returnType = owner.returnType
                val parameterType = owner.valueParameters.single().type
                val extensionType = checkNotNull(owner.extensionReceiverParameter).type
                val origin = owner.origin
                rejectMutation("dispatch", { call.insertDispatchReceiver(receiver) }, { call.removeDispatchReceiver() })
                rejectMutation("super", { call.superQualifierSymbol = receiverType.classOrNull }, { call.superQualifierSymbol = null })
                rejectMutation("missing receiver", { call.extensionReceiver = null }, { call.extensionReceiver = receiver })
                rejectMutation("nullable receiver", { receiver.type = receiverType.makeNullable() }, { receiver.type = receiverType })
                rejectMutation("wrong receiver", { receiver.type = intType }, { receiver.type = receiverType })
                rejectMutation("missing predicate", { call.putValueArgument(0, null) }, { call.putValueArgument(0, predicate) })
                rejectMutation("wrong predicate", { predicate.type = booleanType }, { predicate.type = predicateType })
                rejectMutation("nullable predicate", { predicate.type = predicateType.makeNullable() }, { predicate.type = predicateType })
                rejectMutation("missing type argument", { call.putTypeArgument(0, null) }, { call.putTypeArgument(0, typeArgument) })
                rejectMutation("wrong type argument", { call.putTypeArgument(0, booleanType) }, { call.putTypeArgument(0, typeArgument) })
                rejectMutation("declaration result", { owner.returnType = booleanType }, { owner.returnType = returnType })
                rejectMutation("declaration predicate", { owner.valueParameters.single().type = booleanType },
                    { owner.valueParameters.single().type = parameterType })
                rejectMutation("declaration receiver", { owner.extensionReceiverParameter!!.type = intType },
                    { owner.extensionReceiverParameter!!.type = extensionType })
                rejectMutation("source declaration", { owner.origin = IrDeclarationOrigin.DEFINED }, { owner.origin = origin })
            }
            if (emitted is EtsCall) {
                val badType = if (emitted.type == EtsTypes.BOOLEAN) EtsTypes.NUMBER else EtsTypes.BOOLEAN
                val failure = runCatching { language.validate(emitted.copy(type = badType)) }.exceptionOrNull()
                check(failure is InvalidTarget && failure.message == "Target call result differs from its signature") {
                    "Validator accepted an invalid stdlib target-call result"
                }
                check(failure.source == language.source(call))
                invalidTargetResults++
            }
            // Mutate only the result type of a genuine compiler call, then restore it.
            // Such malformed IR must not cause a rule to invent a valid-looking result.
            val original = call.type
            val alternatives = listOf(if (original.isBoolean()) intType else booleanType) +
                listTypes.filter { it != original && original.classOrNull == it.classOrNull }
            try {
                for (badType in alternatives) {
                    call.type = badType
                    val badLanguage = RecordingLanguage(file)
                    check(rules.lower(call, badLanguage, Scope()) == null) {
                        "Accepted malformed IR result for " + symbolName(call.symbol.owner)
                    }
                    check(badLanguage.inputs.isEmpty()) { "Malformed result lowered children" }
                    invalidIrResults++
                }
            } finally {
                call.type = original
            }
        }
        check(accepted + rejected > 0) { "No compiler calls tested" }
        check(rejected == expectedRejections) { "Unexpected rejection count: " + rejected }
        if (expectedRejections == 0) check(invalidTargetResults > 0)
        if (expectedRejections == 0) check(invalidFilters == 42) { "Filter signature mutation coverage: $invalidFilters" }
        println("PASS: " + accepted + " accepted calls, " + rejected + " rejected calls; " +
            invalidIrResults + " malformed IR results and " + invalidTargetResults + " malformed target-call results rejected; " +
            invalidFilters + " malformed filter dispatch/signatures rejected")
    } finally {
        messages.flush()
        Disposer.dispose(disposable)
    }
}

private class RecordingLanguage(private val file: String) : Language {
    val inputs = mutableListOf<EtsSymbol>()
    override fun source(element: IrElement) = SourceSpan(file, element.startOffset, element.endOffset)
    override fun type(type: IrType): EtsType {
        val simple = type as? IrSimpleType ?: error("Unsupported probe type")
        val arguments = simple.arguments.map { (it as IrTypeProjection).type }
        val name = simple.classOrNull?.owner?.fqNameWhenAvailable?.asString()
        val result = when (name) {
            "kotlin.Int" -> EtsTypes.NUMBER
            "kotlin.Boolean" -> EtsTypes.BOOLEAN
            "kotlin.String" -> EtsTypes.STRING
            "kotlin.collections.List", "kotlin.collections.MutableList", "kotlin.collections.Iterable" ->
                EtsNamedType("Array", listOf(type(arguments.single())))
            "kotlin.Function1" -> EtsFunctionType(listOf(type(arguments[0])), type(arguments[1]))
            else -> error("Unsupported probe classifier: " + name)
        }
        return if (type.isNullable()) EtsNullableType(result) else result
    }
    override fun expression(expression: IrExpression, scope: Scope): EtsExpression {
        val name = "input" + inputs.size
        val symbol = EtsSymbol(name, name, type(expression.type), source(expression))
        inputs.add(symbol)
        return EtsReference(symbol)
    }
    fun validate(expression: EtsExpression) {
        val function = EtsFunction("probe", inputs.map { EtsParameter(it) }, expression.type,
            listOf(EtsReturn(expression, expression.source)), expression.source)
        EtsValidator().validate(EtsProgram(listOf(EtsFile(file, listOf(function)))))
    }
    override fun statements(body: IrBody, scope: Scope): List<EtsStatement> = error("Unexpected statements")
    override fun function(function: IrSimpleFunction, scope: Scope): EtsFunction = error("Unexpected function")
    override fun clazz(declaration: IrClass): EtsClass = error("Unexpected class")
}
