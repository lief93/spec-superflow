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
        target.checkArguments(call, setOf("painter", "contentDescription", "modifier", "tint"))
        val painter = argument(call, "painter") ?: target.diagnostics.unsupported(call, "Icon requires supported Painter overload")
        val tint = argument(call, "tint") ?: target.diagnostics.unsupported(call, "Icon default tint requires LocalContentColor; provide explicit tint")
        val attrs = imageDescription(call, language, scope, target).toMutableList()
        attrs += target.attribute("objectFit", listOf(target.enumValue("ImageFit", "Contain", call)), call)
        val property = (tint as? IrCall)?.symbol?.owner?.correspondingPropertySymbol?.owner?.let(::symbolName)
        if (property != "androidx.compose.ui.graphics.Color.Companion.Unspecified") {
            val filter = target.call("__etsImageTint", listOf(color(tint, scope)), call,
                listOf(EtsTypes.NUMBER), EtsNamedType("ColorFilter"), identity = "compose:imageTint")
            attrs += target.attribute("colorFilter", listOf(filter), call)
        }
        return ComposeElement(target.native("Image", listOf(language.expression(painter, scope)), call).copy(attributes = attrs))
    }
}
