@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.types.IrType
import org.jetbrains.kotlin.ir.types.classOrNull

/** The supported shapes use ArkUI's normalized uniform corner radius. */
internal class ComposeShapeRule : CallRule {
    override fun mapType(type: IrType, language: Language): EtsType? {
        val owner = type.classOrNull?.owner ?: return null
        return if (sourceFile(owner) == null && symbolName(owner) in setOf(
            "androidx.compose.ui.graphics.Shape", "androidx.compose.foundation.shape.RoundedCornerShape",
            "androidx.compose.foundation.shape.CornerBasedShape")) EtsTypes.STRING else null
    }
    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        val function = call.symbol.owner
        if (sourceFile(function) != null) return null
        if (symbolName(function) == "androidx.compose.foundation.shape.RoundedCornerShape" &&
            function.valueParameters.size == 1 &&
            function.valueParameters.single().type.classOrNull?.owner?.let(::symbolName) == "androidx.compose.ui.unit.Dp") {
            val size = call.getValueArgument(0) ?: return null
            return EtsBinary("+", language.expression(size, scope), EtsLiteral("vp", EtsTypes.STRING, language.source(call)),
                EtsTypes.STRING, language.source(call))
        }
        val property = function.correspondingPropertySymbol?.owner ?: return null
        if (property.getter?.symbol != function.symbol) return null
        val radius = when (symbolName(property)) {
            "androidx.compose.foundation.shape.CircleShape" -> "50%"
            "androidx.compose.ui.graphics.RectangleShape" -> "0vp"
            else -> return null
        }
        return EtsLiteral(radius, EtsTypes.STRING, language.source(call))
    }
}
