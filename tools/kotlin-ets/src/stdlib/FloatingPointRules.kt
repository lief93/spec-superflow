@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.IrBuiltIns
import org.jetbrains.kotlin.ir.declarations.IrDeclarationOrigin
import org.jetbrains.kotlin.ir.types.*
import org.jetbrains.kotlin.ir.util.fqNameWhenAvailable
import org.jetbrains.kotlin.ir.util.isNullable

internal object FloatingPointRules : CallRule {
    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        val owner = call.symbol.owner
        if (sourceFile(owner) != null || owner.isSuspend || owner.isFakeOverride ||
            owner.typeParameters.isNotEmpty() || call.typeArgumentsCount != 0 ||
            call.superQualifierSymbol != null || owner.extensionReceiverParameter != null ||
            call.extensionReceiver != null || owner.valueParameters.size != call.valueArgumentsCount) return null
        val args = (0 until call.valueArgumentsCount).map { call.getValueArgument(it) ?: return null }
        val name = symbolName(owner)
        if (owner.valueParameters.zip(args).any { (parameter, value) ->
                parameter.type != (if (name == "kotlin.internal.ir.ieee754equals") value.type.makeNullable() else value.type) ||
                    parameter.varargElementType != null || parameter.defaultValue != null
            } || owner.returnType != call.type) return null
        val receiver = call.dispatchReceiver
        if (owner.dispatchReceiverParameter?.type != receiver?.type) return null
        if (owner.origin != (if (receiver == null) IrBuiltIns.BUILTIN_OPERATOR
            else IrDeclarationOrigin.IR_EXTERNAL_DECLARATION_STUB)) return null
        val source = language.source(call)
        fun lower(value: IrExpression) = language.expression(value, scope)
        fun number(value: Int) = EtsLiteral(value, EtsTypes.NUMBER, source)
        fun binary(op: String, left: EtsExpression, right: EtsExpression, type: EtsType = EtsTypes.NUMBER) =
            EtsBinary(op, left, right, type, source)
        fun math(method: String, values: List<EtsExpression>): EtsExpression {
            val target = EtsReference(EtsSymbol("stdlib:Math", "Math", EtsNamedType("Math"), source, external = true))
            return EtsCall(EtsMember(target, method, EtsFunctionType(List(values.size) { EtsTypes.NUMBER },
                EtsTypes.NUMBER), source), values, EtsTypes.NUMBER, source)
        }
        fun round(value: EtsExpression) = math("fround", listOf(value))
        val resultType = call.type.numericName()
        if (receiver == null) {
            val relation = relations[name] ?: return null
            if (!call.type.isBoolean() || args.size != 2 || args[0].type != args[1].type ||
                args[0].type.numericName() !in floatingTypes) return null
            return binary(relation, lower(args[0]), lower(args[1]), EtsTypes.BOOLEAN)
        }
        val receiverType = receiver.type.numericName() ?: return null
        if (name != "$receiverType.${owner.name.asString()}") return null
        val method = owner.name.asString()
        if (args.isEmpty()) {
            if (method == "toDouble" && resultType == "kotlin.Double") return lower(receiver)
            if (method == "toFloat" && resultType == "kotlin.Float") return round(lower(receiver))
            if (method == "toInt" && receiverType in floatingTypes && resultType == "kotlin.Int") {
                // Kotlin/JS also uses a conversion intrinsic: truncation alone does not saturate.
                val truncated = math("trunc", listOf(lower(receiver)))
                val clamped = math("max", listOf(number(Int.MIN_VALUE),
                    math("min", listOf(number(Int.MAX_VALUE), truncated))))
                return binary("|", clamped, number(0))
            }
            if (receiverType !in floatingTypes || resultType != receiverType) return null
            val value = when (method) {
                "unaryPlus" -> EtsUnary("+", lower(receiver), EtsTypes.NUMBER, source)
                "unaryMinus" -> EtsUnary("-", lower(receiver), EtsTypes.NUMBER, source)
                "inc" -> binary("+", lower(receiver), number(1))
                "dec" -> binary("-", lower(receiver), number(1))
                else -> return null
            }
            return if (resultType == "kotlin.Float") round(value) else value
        }
        val operator = arithmetic[method] ?: return null
        if (args.size != 1 || resultType !in floatingTypes) return null
        val argumentType = args[0].type.numericName() ?: return null
        val promoted = if (receiverType == "kotlin.Double" || argumentType == "kotlin.Double") "kotlin.Double"
            else if (receiverType == "kotlin.Float" || argumentType == "kotlin.Float") "kotlin.Float" else return null
        if (resultType != promoted) return null
        // JVM Float operations convert integral operands before the operation, then round its result.
        fun operand(value: IrExpression): EtsExpression = if (resultType == "kotlin.Float" &&
            value.type.numericName() != "kotlin.Float") round(lower(value)) else lower(value)
        val value = binary(operator, operand(receiver), operand(args[0]))
        return if (resultType == "kotlin.Float") round(value) else value
    }
}

private val floatingTypes = setOf("kotlin.Float", "kotlin.Double")
private val numericTypes = floatingTypes + setOf("kotlin.Byte", "kotlin.Short", "kotlin.Int")
private fun IrType.numericName(): String? = if (this !is IrSimpleType || arguments.isNotEmpty() || isNullable()) null else
    classOrNull?.owner?.fqNameWhenAvailable?.asString()?.takeIf { it in numericTypes }
private val arithmetic = mapOf("plus" to "+", "minus" to "-", "times" to "*", "div" to "/", "rem" to "%")
private val relations = mapOf("kotlin.internal.ir.less" to "<", "kotlin.internal.ir.lessOrEqual" to "<=",
    "kotlin.internal.ir.greater" to ">", "kotlin.internal.ir.greaterOrEqual" to ">=",
    "kotlin.internal.ir.ieee754equals" to "===")
