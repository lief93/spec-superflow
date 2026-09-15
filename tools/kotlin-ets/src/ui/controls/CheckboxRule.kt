@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.expressions.*

internal class ComposeCheckboxRule(
    private val target: ArkUiCalls,
    decorate: (IrExpression?, Scope, ComposeElement) -> List<EtsStatement>,
) : ComposeControlRule(decorate) {
    override fun control(call: IrCall, language: Language, scope: Scope): ComposeElement? {
        if (symbolName(call.symbol.owner) !in setOf("androidx.compose.material3.Checkbox", "androidx.compose.material.Checkbox")) return null
        if (MATERIAL_CONTEXT in scope.ambientValues) target.diagnostics.unsupported(call,
            "Theme-aware Checkbox colors require a Material checkbox adapter")
        target.checkArguments(call, setOf("checked", "onCheckedChange", "enabled", "modifier"))
        val checked = argument(call, "checked") ?: target.diagnostics.unsupported(call, "Checkbox requires checked")
        val change = argument(call, "onCheckedChange") ?: target.diagnostics.unsupported(call, "Checkbox requires onCheckedChange")
        val attrs = listOf(
            target.attribute("select", listOf(language.expression(checked, scope)), call),
            target.booleanChange(change, scope),
        ) + listOfNotNull(argument(call, "enabled")?.let { target.attribute("enabled", listOf(language.expression(it, scope)), call) })
        return ComposeElement(target.native("Checkbox", emptyList(), call).copy(attributes = attrs),
            setOf("padding", "onClick", "enabled"))
    }
}
