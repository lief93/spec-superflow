@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.*

/** Supported Dp/sp values use native vp/fp scalars; no conversion via physical pixels. */
internal class ComposeDimensionRule : CallRule {
    override fun targetFiles(program: EtsProgram): List<EtsFile> = paddingValueFiles(program)

    override fun mapType(type: IrType, language: Language): EtsType? {
        val owner = type.classOrNull?.owner ?: return null
        return if (sourceFile(owner) == null && symbolName(owner) in setOf(
                "androidx.compose.ui.unit.Dp", "androidx.compose.ui.unit.TextUnit")) EtsTypes.NUMBER else null
    }

    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        val owner = call.symbol.owner
        if (sourceFile(owner) != null) return null
        val property = owner.correspondingPropertySymbol?.owner ?: return null
        if (property.getter?.symbol != owner.symbol) return null
        val name = symbolName(property)
        if (name in setOf("androidx.compose.ui.unit.Dp.Companion.Unspecified",
                "androidx.compose.ui.unit.Dp.Companion.Infinity", "androidx.compose.ui.unit.Dp.Companion.Hairline",
                "androidx.compose.ui.unit.TextUnit.Companion.Unspecified", "androidx.compose.ui.unit.em"))
            throw Unsupported(Diagnostic("UNSUPPORTED", "Unsupported dimension value: $name", language.source(call)))
        if (name in setOf("androidx.compose.ui.unit.Dp.value", "androidx.compose.ui.unit.TextUnit.value")) {
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
            if (!rounded.isFinite()) throw Unsupported(Diagnostic("UNSUPPORTED", "Non-finite dimension value", language.source(call)))
            return EtsLiteral(rounded.toDouble(), EtsTypes.NUMBER, language.source(call))
        }
        val at = language.source(call)
        val math = EtsReference(EtsSymbol("stdlib:Math", "Math", EtsNamedType("Math"), at, true))
        return EtsCall(EtsMember(math, "fround", EtsFunctionType(listOf(EtsTypes.NUMBER), EtsTypes.NUMBER), at),
            listOf(value), EtsTypes.NUMBER, at)
    }
}
