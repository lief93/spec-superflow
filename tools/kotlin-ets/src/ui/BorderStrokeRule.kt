@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.types.IrType
import org.jetbrains.kotlin.ir.types.classOrNull

/** Compose BorderStroke is a portable width/color value, not a control-specific special case. */
internal class ComposeBorderStrokeRule : CallRule {
    override fun mapType(type: IrType, language: Language): EtsType? {
        val owner = type.classOrNull?.owner ?: return null
        return borderStrokeType.takeIf {
            sourceFile(owner) == null && symbolName(owner) == "androidx.compose.foundation.BorderStroke"
        }
    }

    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        if (sourceFile(call.symbol.owner) != null ||
            symbolName(call.symbol.owner) != "androidx.compose.foundation.BorderStroke") return null
        val width = argument(call, "width") ?: return null
        val color = argument(call, "color") ?: return null
        return EtsObject(linkedMapOf(
            "width" to requireSpecifiedDp(language.expression(width, scope), language.source(width), "BorderStroke.width"),
            "color" to requireSpecifiedColor(language.expression(color, scope), language.source(color), "BorderStroke.color"),
        ), borderStrokeType, language.source(call))
    }
}
