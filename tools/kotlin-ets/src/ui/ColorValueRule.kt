@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.*

/** sRGB Color values use the unsigned ARGB representation accepted by ArkUI. */
internal class ComposeColorValueRule : CallRule {
    override fun mapType(type: IrType, language: Language): EtsType? {
        val owner = type.classOrNull?.owner ?: return null
        return if (symbolName(owner) == colorType && sourceFile(owner) == null) EtsTypes.NUMBER else null
    }

    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        val owner = call.symbol.owner
        if (sourceFile(owner) != null) return null
        val name = symbolName(owner)
        val at = language.source(call)
        fun number(value: Long) = EtsLiteral(value, EtsTypes.NUMBER, at)
        val property = owner.correspondingPropertySymbol?.owner?.let(::symbolName)
        colors.entries.firstOrNull { property == "$colorType.Companion.${it.key}" }?.let {
            return number(it.value)
        }
        if (property == "$colorType.Companion.Unspecified") throw Unsupported(Diagnostic(
            "UNSUPPORTED", "Color.Unspecified requires inherited/default color selection; it is not an ARGB value", at))
        if (name == colorType && owner.valueParameters.size == 1) {
            val value = call.getValueArgument(0) ?: return null
            return when (owner.valueParameters.single().type.classOrNull?.owner?.let(::symbolName)) {
                "kotlin.Int" -> EtsBinary(">>>", language.expression(value, scope), number(0), EtsTypes.NUMBER, at)
                // Color(Long) uses only the low 32 bits; do not route it through
                // a lossy general Long-to-number conversion.
                "kotlin.Long" -> (value as? IrConst)?.value?.let { it as? Long }?.let {
                    number(it and 0xFFFFFFFFL)
                }
                else -> null
            }
        }
        if (name == "androidx.compose.ui.graphics.toArgb" && owner.valueParameters.isEmpty()) {
            val receiver = call.extensionReceiver ?: return null
            if (receiver.type.classOrNull?.owner?.let(::symbolName) != colorType) return null
            return EtsBinary("|", language.expression(receiver, scope), number(0), EtsTypes.NUMBER, at)
        }
        return null
    }
}

private const val colorType = "androidx.compose.ui.graphics.Color"
private val colors = mapOf(
    "Black" to 0xFF000000L, "DarkGray" to 0xFF444444L, "Gray" to 0xFF888888L,
    "LightGray" to 0xFFCCCCCCL, "White" to 0xFFFFFFFFL, "Red" to 0xFFFF0000L,
    "Green" to 0xFF00FF00L, "Blue" to 0xFF0000FFL, "Yellow" to 0xFFFFFF00L,
    "Cyan" to 0xFF00FFFFL, "Magenta" to 0xFFFF00FFL, "Transparent" to 0L,
)
