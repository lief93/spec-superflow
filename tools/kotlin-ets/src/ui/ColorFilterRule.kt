@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.*

private val colorFilterType = EtsNamedType("ColorFilter")

/** ColorFilter.tint is the SrcIn matrix already used by Icon; other filter modes remain unsupported. */
internal class ComposeColorFilterRule : CallRule {
    override fun mapType(type: IrType, language: Language): EtsType? {
        val owner = type.classOrNull?.owner ?: return null
        return if (sourceFile(owner) == null && symbolName(owner) == "androidx.compose.ui.graphics.ColorFilter")
            colorFilterType else null
    }

    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        val owner = call.symbol.owner
        if (sourceFile(owner) != null) return null
        if (symbolName(owner) != "androidx.compose.ui.graphics.ColorFilter.Companion.tint" &&
            symbolName(owner) != "androidx.compose.ui.graphics.ColorFilter.tint") return null
        val at = language.source(call)
        val color = argument(call, "color")
            ?: throw Unsupported(Diagnostic("UNSUPPORTED", "ColorFilter.tint requires color", at))
        argument(call, "blendMode")?.let {
            throw Unsupported(Diagnostic("UNSUPPORTED",
                "ColorFilter.tint currently requires the default SrcIn blend", language.source(it)))
        }
        val value = language.expression(color, scope)
        return EtsCall(EtsReference(EtsSymbol("compose:imageTint", "__etsImageTint",
            EtsFunctionType(listOf(EtsTypes.NUMBER), colorFilterType), at, true), at),
            listOf(value), colorFilterType, at)
    }
}
