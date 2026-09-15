@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.expressions.*

internal class ComposeBoxRule(
    private val target: ArkUiCalls,
    private val content: (IrExpression, Scope) -> List<EtsStatement>,
    private val touchBoxes: Map<IrCall, TouchTargets>,
    decorate: (IrExpression?, Scope, ComposeElement) -> List<EtsStatement>,
) : ComposeControlRule(decorate) {
    override fun control(call: IrCall, language: Language, scope: Scope): ComposeElement? {
        if (symbolName(call.symbol.owner) != "androidx.compose.foundation.layout.Box") return null
        target.checkArguments(call, setOf("modifier", "contentAlignment", "content"))
        val children = argument(call, "content")?.let { content(it, scope) } ?: emptyList()
        val alignment = argument(call, "contentAlignment")?.let { language.expression(it, scope) }
            ?: target.enumValue("Alignment", "TopStart", call)
        val options = target.record("StackOptions", linkedMapOf("alignContent" to alignment), call)
        return ComposeElement(target.native("Stack", listOf(options), call, children), touch = touchBoxes[call],
            orderedArguments = listOf(alignment))
    }
}
