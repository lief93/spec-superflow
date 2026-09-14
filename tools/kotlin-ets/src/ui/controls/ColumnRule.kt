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
        target.checkArguments(call, setOf("modifier", "content"))
        val children = argument(call, "content")?.let { content(it, scope) } ?: emptyList()
        return ComposeElement(target.native("Column", emptyList(), call, children).copy(attributes = listOf(
            target.attribute("alignItems", listOf(target.enumValue("HorizontalAlign", "Start", call)), call))))
    }
}
