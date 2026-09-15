@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.expressions.*

internal class ComposeButtonRule(
    private val target: ArkUiCalls,
    private val content: (IrExpression, Scope) -> List<EtsStatement>,
    private val callback: (IrExpression, Scope) -> EtsExpression,
    decorate: (IrExpression?, Scope, ComposeElement) -> List<EtsStatement>,
) : ComposeControlRule(decorate) {
    override fun control(call: IrCall, language: Language, scope: Scope): ComposeElement? {
        if (symbolName(call.symbol.owner) !in setOf("androidx.compose.material3.Button", "androidx.compose.material.Button")) return null
        if (MATERIAL_CONTEXT in scope.ambientValues) target.diagnostics.unsupported(call,
            "Theme-aware Button colors and disabled state require a Material button adapter")
        target.checkArguments(call, setOf("onClick", "modifier", "enabled", "content"))
        val body = argument(call, "content") ?: target.diagnostics.unsupported(call, "Button requires content")
        val click = argument(call, "onClick") ?: target.diagnostics.unsupported(call, "Button requires callback")
        val row = target.native("Row", emptyList(), call, content(body, scope)).copy(attributes = listOf(
            target.attribute("alignItems", listOf(target.enumValue("VerticalAlign", "Center", call)), call),
            target.attribute("justifyContent", listOf(target.enumValue("FlexAlign", "Center", call)), call)))
        val attrs = listOf(target.attribute("onClick", listOf(callback(click, scope)), call)) + listOfNotNull(
            argument(call, "enabled")?.let { target.attribute("enabled", listOf(language.expression(it, scope)), call) })
        return ComposeElement(target.native("Button", emptyList(), call, listOf(row)).copy(attributes = attrs),
            setOf("padding", "backgroundColor", "onClick", "enabled"))
    }
}
