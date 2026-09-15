@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.types.IrType
import org.jetbrains.kotlin.ir.types.classOrNull

/** Logical alignments remain typed values through source methods and parameters. */
internal class ComposeAlignmentRule : CallRule {
    private val types = mapOf("androidx.compose.ui.Alignment" to "Alignment",
        "androidx.compose.ui.Alignment.Horizontal" to "HorizontalAlign",
        "androidx.compose.ui.Alignment.Vertical" to "VerticalAlign")
    private val values = mapOf(
        "TopStart" to ("Alignment" to "TopStart"), "TopCenter" to ("Alignment" to "Top"),
        "TopEnd" to ("Alignment" to "TopEnd"), "CenterStart" to ("Alignment" to "Start"),
        "Center" to ("Alignment" to "Center"), "CenterEnd" to ("Alignment" to "End"),
        "BottomStart" to ("Alignment" to "BottomStart"), "BottomCenter" to ("Alignment" to "Bottom"),
        "BottomEnd" to ("Alignment" to "BottomEnd"),
        "Start" to ("HorizontalAlign" to "Start"), "CenterHorizontally" to ("HorizontalAlign" to "Center"),
        "End" to ("HorizontalAlign" to "End"), "Top" to ("VerticalAlign" to "Top"),
        "CenterVertically" to ("VerticalAlign" to "Center"), "Bottom" to ("VerticalAlign" to "Bottom")
    ).mapKeys { (name, _) -> "androidx.compose.ui.Alignment.Companion.$name" }

    override fun mapType(type: IrType, language: Language): EtsType? {
        val owner = type.classOrNull?.owner ?: return null
        if (sourceFile(owner) != null) return null
        return types[symbolName(owner)]?.let { EtsNamedType(it) }
    }

    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        val owner = call.symbol.owner
        if (sourceFile(owner) != null) return null
        val property = owner.correspondingPropertySymbol?.owner ?: return null
        if (property.getter?.symbol != owner.symbol) return null
        val (type, name) = values[symbolName(property)] ?: return null
        val at = language.source(call)
        val target = EtsNamedType(type)
        return EtsMember(EtsReference(EtsSymbol("arkui:$type", type, target, at, external = true)), name, target, at)
    }
}
