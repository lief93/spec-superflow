@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.expressions.*

internal class ComposeIconRule(
    private val target: ArkUiCalls,
    private val color: (IrExpression, Scope) -> EtsExpression,
    decorate: (IrExpression?, Scope, ComposeElement) -> List<EtsStatement>,
) : ComposeControlRule(decorate) {
    override fun control(call: IrCall, language: Language, scope: Scope): ComposeElement? {
        if (symbolName(call.symbol.owner) !in setOf("androidx.compose.material.Icon", "androidx.compose.material3.Icon")) return null
        target.checkArguments(call, setOf("painter", "imageVector", "contentDescription", "modifier", "tint"))
        val painter = argument(call, "painter")
        val imageVector = argument(call, "imageVector")
        if ((painter == null) == (imageVector == null))
            target.diagnostics.unsupported(call, "Icon requires exactly one supported Painter or ImageVector value")
        val explicit = argument(call, "tint")
        val unspecified = (explicit as? IrCall)?.symbol?.owner?.correspondingPropertySymbol?.owner?.let(::symbolName) ==
            "androidx.compose.ui.graphics.Color.Companion.Unspecified"
        val tint = when {
            unspecified -> null
            explicit != null -> color(explicit, scope)
            symbolName(call.symbol.owner) == "androidx.compose.material3.Icon" ->
                scope.ambientValues[MATERIAL_CONTEXT]?.let { materialContentColor(it, language.source(call)) }
                    ?: target.diagnostics.unsupported(call, "Icon default tint requires LocalContentColor; provide explicit tint")
            else -> target.diagnostics.unsupported(call, "Icon default tint requires LocalContentColor; provide explicit tint")
        }
        val attrs = imageDescription(call, language, scope, target).toMutableList()
        if (painter != null) {
            attrs += target.attribute("objectFit", listOf(target.enumValue("ImageFit", "Contain", call)), call)
            if (tint != null) {
                val filter = target.call("__etsImageTint", listOf(tint), call,
                    listOf(EtsTypes.NUMBER), EtsNamedType("ColorFilter"), identity = "compose:imageTint")
                attrs += target.attribute("colorFilter", listOf(filter), call)
            }
            return ComposeElement(target.native("Image", listOf(language.expression(painter, scope)), call).copy(attributes = attrs))
        }
        val vector = language.expression(imageVector!!, scope)
        if (vector.type != materialImageVectorType)
            target.diagnostics.unsupported(imageVector, "Icon ImageVector requires a mapped Material icon")
        val resource = EtsMember(vector, "resource", materialImageVectorResourceType, language.source(imageVector))
        attrs += target.attribute("fontSize", listOf(target.literal(24, call)), call)
        attrs += target.attribute("width", listOf(target.literal(24, call)), call)
        attrs += target.attribute("height", listOf(target.literal(24, call)), call)
        if (tint != null) attrs += target.attribute("fontColor",
            listOf(EtsArray(listOf(tint), EtsTypes.NUMBER, language.source(call))), call)
        return ComposeElement(target.native("SymbolGlyph", listOf(resource), call).copy(attributes = attrs))
    }
}
