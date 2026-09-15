@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.expressions.*

internal class ComposeHorizontalDividerRule(
    private val target: ArkUiCalls,
    private val color: (IrExpression, Scope) -> EtsExpression,
    private val dimension: (IrExpression, Scope, String) -> EtsExpression,
    decorate: (IrExpression?, Scope, ComposeElement) -> List<EtsStatement>,
) : ComposeControlRule(decorate) {
    override fun control(call: IrCall, language: Language, scope: Scope): ComposeElement? {
        if (symbolName(call.symbol.owner) !in setOf("androidx.compose.material3.HorizontalDivider",
                "androidx.compose.material3.Divider", "androidx.compose.material.Divider")) return null
        target.checkArguments(call, setOf("modifier", "thickness", "color"))
        if (MATERIAL_CONTEXT in scope.ambientValues && argument(call, "color") == null)
            target.diagnostics.unsupported(call, "Theme-aware Divider default color requires Material divider tokens")
        val thickness = argument(call, "thickness")?.let { dimension(it, scope, "dp") } ?: target.literal(1, call)
        if (thickness !is EtsLiteral && thickness !is EtsReference)
            target.diagnostics.unsupported(call, "Divider needs a stable thickness value for both stroke and layout")
        val attrs = listOf(
            target.attribute("vertical", listOf(target.literal(false, call)), call),
            target.attribute("strokeWidth", listOf(thickness), call),
            target.attribute("width", listOf(target.literal("100%", call)), call),
            target.attribute("height", listOf(thickness), call),
        ) + listOfNotNull(argument(call, "color")?.let { target.attribute("color", listOf(color(it, scope)), call) })
        return ComposeElement(target.native("Divider", emptyList(), call).copy(attributes = attrs),
            setOf("padding", "width", "height"))
    }
}
