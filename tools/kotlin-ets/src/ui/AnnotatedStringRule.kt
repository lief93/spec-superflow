@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.declarations.IrClass
import org.jetbrains.kotlin.ir.declarations.IrFunction
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.*

internal class ComposeAnnotatedStringRule : CallRule {
    override fun targetFiles(program: EtsProgram) = annotatedStringFiles(program)

    override fun mapType(type: IrType, language: Language): EtsType? {
        val owner = type.classOrNull?.owner ?: return null
        if (sourceFile(owner) != null) return null
        return when (symbolName(owner)) {
            "androidx.compose.ui.text.SpanStyle" -> spanStyleType
            "androidx.compose.ui.text.AnnotatedString" -> annotatedStringType
            "androidx.compose.ui.text.AnnotatedString.Builder" -> annotatedBuilderType
            "androidx.compose.ui.text.AnnotatedString.Range" -> annotatedSpanType
            else -> null
        }
    }

    override fun lowerConstructor(call: IrConstructorCall, language: Language, scope: Scope): EtsExpression? {
        val owner = call.symbol.owner.parent as? IrClass ?: return null
        if (sourceFile(owner) != null) return null
        val at = language.source(call)
        return when (symbolName(owner)) {
            "androidx.compose.ui.text.SpanStyle" -> {
                call.symbol.owner.valueParameters.forEachIndexed { index, parameter ->
                    if (parameter.name.asString() !in spanStyleFields && call.getValueArgument(index) != null)
                        reject(call, language, "Unsupported SpanStyle argument: ${parameter.name}")
                }
                EtsNew(spanStyleType, spanStyleFields.keys.map { name ->
                    argument(call, name)?.let { language.expression(it, scope) } ?: EtsLiteral(null, EtsTypes.NULL, at)
                }, at)
            }
            "androidx.compose.ui.text.AnnotatedString.Builder" -> {
                if ((0 until call.valueArgumentsCount).any { call.getValueArgument(it) != null })
                    reject(call, language, "AnnotatedString.Builder currently requires the empty constructor")
                EtsNew(annotatedBuilderType, emptyList(), at)
            }
            "androidx.compose.ui.text.AnnotatedString" -> {
                val text = argument(call, "text") ?: return null
                if (!text.type.isString()) return null
                if ((0 until call.valueArgumentsCount).filter { call.symbol.owner.valueParameters[it].name.asString() != "text" }
                        .any { call.getValueArgument(it) != null })
                    reject(call, language, "AnnotatedString currently requires a plain String")
                EtsNew(annotatedStringType, listOf(language.expression(text, scope),
                    EtsArray(emptyList(), annotatedSpanType, at)), at)
            }
            else -> null
        }
    }

    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        val owner = call.symbol.owner
        val api = symbolName(owner)
        val at = language.source(call)
        // Top-level Compose text helpers are binary file facades; their IrFile provenance
        // is not application source and must not hide the FQ-name match.
        if (api == "androidx.compose.ui.text.buildAnnotatedString") {
            val block = lambda(argument(call, "builder") ?: call.getValueArgument(0), scope)
                ?: reject(call, language, "buildAnnotatedString requires a source builder lambda")
            return buildAnnotated(block, language, scope, at)
        }
        val receiver = call.dispatchReceiver ?: call.extensionReceiver
        if (api == "androidx.compose.ui.text.withStyle" ||
            api == "androidx.compose.ui.text.AnnotatedString.Builder.withStyle") {
            val builder = receiver ?: reject(call, language, "withStyle requires an AnnotatedString.Builder receiver")
            val style = argument(call, "style") ?: reject(call, language, "withStyle requires style")
            if (style.type.classOrNull?.owner?.let(::symbolName) != "androidx.compose.ui.text.SpanStyle")
                reject(style, language, "withStyle currently requires SpanStyle")
            val block = lambda(argument(call, "block") ?: call.getValueArgument(1), scope)
                ?: reject(call, language, "withStyle requires a source lambda")
            return withStyle(builder, style, block, language, scope, at)
        }
        if (sourceFile(owner) != null) return null
        val receiverType = receiver?.type?.classOrNull?.owner?.let(::symbolName)
        if (receiver != null && receiverType == "androidx.compose.ui.text.AnnotatedString.Builder") {
            val target = language.expression(receiver, scope)
            return when (owner.name.asString()) {
                "append" -> {
                    val value = call.getValueArgument(0) ?: return null
                    if (!value.type.isString()) reject(value, language, "AnnotatedString.Builder.append currently requires String")
                    member(target, "append", listOf(EtsTypes.STRING), EtsTypes.VOID, listOf(language.expression(value, scope)), at)
                }
                "pushStyle" -> {
                    val style = argument(call, "style") ?: call.getValueArgument(0) ?: return null
                    member(target, "pushStyle", listOf(spanStyleType), EtsTypes.NUMBER, listOf(language.expression(style, scope)), at)
                }
                "pushStringAnnotation" -> {
                    val tag = argument(call, "tag") ?: reject(call, language, "pushStringAnnotation requires tag")
                    val annotation = argument(call, "annotation") ?: reject(call, language, "pushStringAnnotation requires annotation")
                    member(target, "pushStringAnnotation", listOf(EtsTypes.STRING, EtsTypes.STRING), EtsTypes.NUMBER,
                        listOf(language.expression(tag, scope), language.expression(annotation, scope)), at)
                }
                "pop" -> member(target, "pop", emptyList(), EtsTypes.VOID, emptyList(), at)
                "toAnnotatedString" -> member(target, "toAnnotatedString", emptyList(), annotatedStringType, emptyList(), at)
                else -> null
            }
        }
        if (receiver != null && receiverType == "androidx.compose.ui.text.AnnotatedString" &&
            owner.name.asString() == "getStringAnnotations") {
            if (argument(call, "tag") != null) reject(call, language, "Tagged getStringAnnotations is not mapped")
            val start = argument(call, "start") ?: call.getValueArgument(0) ?: return null
            val end = argument(call, "end") ?: call.getValueArgument(1) ?: return null
            val result = annotatedSpansType
            return EtsCall(EtsReference(annotatedGetFunction.symbol, at), listOf(language.expression(receiver, scope),
                language.expression(start, scope), language.expression(end, scope)), result, at)
        }
        val property = owner.correspondingPropertySymbol?.owner ?: return null
        if (property.getter?.symbol != owner.symbol) return null
        val parent = property.parent as? IrClass ?: return null
        val name = property.name.asString()
        if (symbolName(parent) == "androidx.compose.ui.text.SpanStyle" && name in spanStyleFields) {
            return EtsMember(language.expression(call.dispatchReceiver ?: return null, scope), name,
                spanStyleFields.getValue(name), at)
        }
        if (symbolName(parent) == "androidx.compose.ui.text.AnnotatedString.Range" && name in annotatedSpanFields) {
            return EtsMember(language.expression(call.dispatchReceiver ?: return null, scope), name,
                annotatedSpanFields.getValue(name), at)
        }
        if (symbolName(parent) == "androidx.compose.ui.text.AnnotatedString" && name == "text") {
            return EtsMember(language.expression(call.dispatchReceiver ?: return null, scope), "text", EtsTypes.STRING, at)
        }
        return null
    }

    override fun lowerStatement(call: IrCall, language: Language, scope: Scope): List<EtsStatement>? {
        val value = lower(call, language, scope) ?: return null
        return if (value.type == EtsTypes.VOID) listOf(EtsExpressionStatement(value)) else null
    }

    private fun buildAnnotated(block: IrFunction, language: Language, scope: Scope, at: SourceSpan): EtsExpression {
        val builder = EtsSymbol("annotated:${at.file}:${at.start}:builder", "builder", annotatedBuilderType, at)
        val child = scope.fork()
        val receiver = block.extensionReceiverParameter
            ?: throw Unsupported(Diagnostic("UNSUPPORTED", "buildAnnotatedString requires a Builder receiver", at))
        child.bindings[receiver.symbol] = EtsReference(builder)
        val body = language.statements(block.body ?: throw Unsupported(Diagnostic("UNSUPPORTED",
            "buildAnnotatedString requires a source body", at)), child)
        val constructed = EtsNew(annotatedBuilderType, emptyList(), at)
        val result = EtsCall(EtsMember(EtsReference(builder), "toAnnotatedString",
            EtsFunctionType(emptyList(), annotatedStringType), at), emptyList(), annotatedStringType, at)
        return EtsCall(EtsLambda(emptyList(), listOf(EtsVariable(builder, constructed, false)) + body +
            listOf(EtsReturn(result, at)), annotatedStringType, at), emptyList(), annotatedStringType, at)
    }

    private fun withStyle(builder: IrExpression, style: IrExpression, block: IrFunction,
        language: Language, scope: Scope, at: SourceSpan): EtsExpression {
        val target = language.expression(builder, scope)
        val push = member(target, "pushStyle", listOf(spanStyleType), EtsTypes.NUMBER, listOf(language.expression(style, scope)), at)
        val child = scope.fork()
        block.extensionReceiverParameter?.let { child.bindings[it.symbol] = target }
        val body = language.statements(block.body ?: throw Unsupported(Diagnostic("UNSUPPORTED",
            "withStyle requires a source body", at)), child)
        val pop = member(target, "pop", emptyList(), EtsTypes.VOID, emptyList(), at)
        val result = if (block.returnType.isUnit()) EtsTypes.VOID else language.type(block.returnType)
        val lines = listOf(EtsExpressionStatement(push)) + body + listOf(EtsExpressionStatement(pop))
        return if (result == EtsTypes.VOID) EtsCall(EtsLambda(emptyList(), lines, EtsTypes.VOID, at), emptyList(), EtsTypes.VOID, at)
        else reject(style, language, "withStyle currently requires a Unit builder lambda")
    }

    private fun member(target: EtsExpression, name: String, parameters: List<EtsType>, result: EtsType,
        arguments: List<EtsExpression>, at: SourceSpan) =
        EtsCall(EtsMember(target, name, EtsFunctionType(parameters, result), at), arguments, result, at)

    private fun reject(value: IrExpression, language: Language, message: String): Nothing =
        throw Unsupported(Diagnostic("UNSUPPORTED", message, language.source(value)))
}
