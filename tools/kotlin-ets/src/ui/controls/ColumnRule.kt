@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.expressions.*

internal class ComposeColumnRule(
    private val target: ArkUiCalls,
    private val content: (IrExpression, Scope) -> List<EtsStatement>,
    decorate: (IrExpression?, Scope, ComposeElement) -> List<EtsStatement>,
) : ComposeControlRule(decorate) {
    override fun control(call: IrCall, language: Language, scope: Scope): ComposeElement? {
        if (symbolName(call.symbol.owner) != "androidx.compose.foundation.layout.Column") return null
        target.checkArguments(call, setOf("modifier", "horizontalAlignment", "content"))
        val children = argument(call, "content")?.let { content(it, scope) } ?: emptyList()
        val alignment = argument(call, "horizontalAlignment")?.let { language.expression(it, scope) }
            ?: target.enumValue("HorizontalAlign", "Start", call)
        return ComposeElement(target.native("Column", emptyList(), call, children).copy(attributes = listOf(
            target.attribute("alignItems", listOf(alignment), call))), orderedArguments = listOf(alignment))
    }
}
