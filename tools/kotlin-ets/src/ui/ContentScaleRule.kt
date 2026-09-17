@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.types.IrType
import org.jetbrains.kotlin.ir.types.classOrNull

/** Image fit is a platform value, including when passed through source helpers. */
internal class ComposeContentScaleRule : CallRule {
    private val sourceType = "androidx.compose.ui.layout.ContentScale"
    private val targetType = EtsNamedType("ImageFit")
    private val values = mapOf("Fit" to "Contain", "Crop" to "Cover", "FillBounds" to "Fill",
        "Inside" to "ScaleDown", "None" to "None")

    override fun mapType(type: IrType, language: Language): EtsType? {
        val owner = type.classOrNull?.owner ?: return null
        return if (sourceFile(owner) == null && symbolName(owner) == sourceType) targetType else null
    }

    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        val owner = call.symbol.owner
        if (sourceFile(owner) != null) return null
        val property = owner.correspondingPropertySymbol?.owner ?: return null
        if (property.getter?.symbol != owner.symbol) return null
        val propertyName = symbolName(property)
        if (!propertyName.startsWith("$sourceType.Companion.")) return null
        val name = values.entries.firstOrNull { propertyName == "$sourceType.Companion.${it.key}" }?.value
            ?: throw Unsupported(Diagnostic("UNSUPPORTED", "Unsupported ContentScale: $propertyName", language.source(call)))
        val at = language.source(call)
        return EtsMember(EtsReference(EtsSymbol("arkui:ImageFit", "ImageFit", targetType, at, external = true)), name, targetType, at)
    }
}
