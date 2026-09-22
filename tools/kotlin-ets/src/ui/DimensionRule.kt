@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.*

/** Supported Dp/sp values use native vp/fp scalars; no conversion via physical pixels. */
internal val composeDpType = EtsNullableType(EtsTypes.NUMBER)

/** Produces a concrete vp value once or fails at the source operation that requires one. */
internal fun requireSpecifiedDp(value: EtsExpression, at: SourceSpan, consumer: String): EtsExpression {
    if (value.type == EtsTypes.NULL || value is EtsLiteral && value.value == null)
        throw Unsupported(Diagnostic("UNSUPPORTED", "$consumer requires a specified Dp value", at))
    if (value.type == EtsTypes.NUMBER) return value
    if (value.type != composeDpType)
        throw Unsupported(Diagnostic("UNSUPPORTED", "$consumer requires a Dp value; got ${value.type}", at))
    val parameter = EtsParameter(EtsSymbol("compose:requiredDp:${at.file}:${at.start}", "dimension", composeDpType, at))
    val reference = EtsReference(parameter.symbol)
    val message = EtsLiteral("$consumer received Dp.Unspecified at ${at.file ?: "<unknown>"}:${at.start}",
        EtsTypes.STRING, at)
    return EtsCall(EtsLambda(listOf(parameter), listOf(
        EtsIf(listOf(EtsBranch(EtsBinary("===", reference, EtsLiteral(null, EtsTypes.NULL, at),
            EtsTypes.BOOLEAN, at), listOf(EtsThrow(namedTargetFailure("UnspecifiedDp", at, message), at)))), at),
        EtsReturn(EtsCast(reference, EtsTypes.NUMBER, at), at)), EtsTypes.NUMBER, at),
        listOf(value), EtsTypes.NUMBER, at)
}

internal class ComposeDimensionRule : CallRule {
    override fun targetFiles(program: EtsProgram): List<EtsFile> = paddingValueFiles(program)

    override fun mapType(type: IrType, language: Language): EtsType? {
        val owner = type.classOrNull?.owner ?: return null
        if (sourceFile(owner) != null) return null
        return when (symbolName(owner)) {
            "androidx.compose.ui.unit.Dp" -> composeDpType
            "androidx.compose.ui.unit.TextUnit" -> EtsTypes.NUMBER
            else -> null
        }
    }

    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        val owner = call.symbol.owner
        if (sourceFile(owner) != null) return null
        val api = symbolName(owner)
        val at = language.source(call)
        if (api == "kotlin.internal.ir.EQEQ" && call.valueArgumentsCount == 2) {
            val left = call.getValueArgument(0) ?: return null
            val right = call.getValueArgument(1) ?: return null
            if (listOf(left, right).all {
                    it.type.classOrNull?.owner?.let(::symbolName) == "androidx.compose.ui.unit.Dp" })
                return EtsBinary("===", language.expression(left, scope), language.expression(right, scope),
                    EtsTypes.BOOLEAN, at)
        }
        val property = owner.correspondingPropertySymbol?.owner ?: return null
        if (property.getter?.symbol != owner.symbol) return null
        val name = symbolName(property)
        if (name == "androidx.compose.ui.unit.Dp.Companion.Unspecified")
            return EtsLiteral(null, EtsTypes.NULL, at)
        if (name in setOf("androidx.compose.ui.unit.Dp.Companion.Infinity", "androidx.compose.ui.unit.Dp.Companion.Hairline",
                "androidx.compose.ui.unit.TextUnit.Companion.Unspecified", "androidx.compose.ui.unit.em"))
            throw Unsupported(Diagnostic("UNSUPPORTED", "Unsupported dimension value: $name", at))
        if (name == "androidx.compose.ui.unit.Dp.value") {
            val receiver = call.dispatchReceiver ?: return null
            return requireSpecifiedDp(language.expression(receiver, scope), at, "Dp.value")
        }
        if (name == "androidx.compose.ui.unit.TextUnit.value") {
            val receiver = call.dispatchReceiver ?: return null
            return language.expression(receiver, scope)
        }
        if (name !in setOf("androidx.compose.ui.unit.dp", "androidx.compose.ui.unit.sp")) return null
        val receiver = call.extensionReceiver ?: return null
        if (receiver.type.classFqName?.asString() !in setOf("kotlin.Int", "kotlin.Float", "kotlin.Double")) return null
        val value = language.expression(receiver, scope)
        if (receiver.type.isFloat()) return value
        // AndroidX's Int/Double unit getters convert to Float before storing the value.
        if (value is EtsLiteral && value.value is Number) {
            val rounded = value.value.toFloat()
            if (!rounded.isFinite()) throw Unsupported(Diagnostic("UNSUPPORTED", "Non-finite dimension value", at))
            return EtsLiteral(rounded.toDouble(), EtsTypes.NUMBER, at)
        }
        val math = EtsReference(EtsSymbol("stdlib:Math", "Math", EtsNamedType("Math"), at, true))
        return EtsCall(EtsMember(math, "fround", EtsFunctionType(listOf(EtsTypes.NUMBER), EtsTypes.NUMBER), at),
            listOf(value), EtsTypes.NUMBER, at)
    }
}
