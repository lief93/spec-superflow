@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.expressions.*

internal class ComposeSwitchRule(
    private val target: ArkUiCalls,
    decorate: (IrExpression?, Scope, ComposeElement) -> List<EtsStatement>,
) : ComposeControlRule(decorate) {
    override fun control(call: IrCall, language: Language, scope: Scope): ComposeElement? {
        if (symbolName(call.symbol.owner) !in setOf("androidx.compose.material3.Switch", "androidx.compose.material.Switch")) return null
        if (MATERIAL_CONTEXT in scope.ambientValues) target.diagnostics.unsupported(call,
            "Theme-aware Switch colors require a Material switch adapter")
        target.checkArguments(call, setOf("checked", "onCheckedChange", "enabled", "modifier"))
        val checked = argument(call, "checked") ?: target.diagnostics.unsupported(call, "Switch requires checked")
        val change = argument(call, "onCheckedChange") ?: target.diagnostics.unsupported(call, "Switch requires onCheckedChange")
        val options = target.record("ToggleOptions", linkedMapOf(
            "type" to target.enumValue("ToggleType", "Switch", call),
            "isOn" to language.expression(checked, scope)), call)
        val attrs = listOf(target.booleanChange(change, scope)) +
            listOfNotNull(argument(call, "enabled")?.let { target.attribute("enabled", listOf(language.expression(it, scope)), call) })
        return ComposeElement(target.native("Toggle", listOf(options), call).copy(attributes = attrs),
            setOf("padding", "onClick", "enabled"))
    }
}
