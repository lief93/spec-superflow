@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.expressions.*

internal class ComposeColumnRule(
    private val target: ArkUiCalls,
    private val content: (IrExpression, Scope) -> List<EtsStatement>,
    private val contentFlags: (IrExpression?, Scope) -> Set<String>,
    decorate: (IrExpression?, Scope, ComposeElement) -> List<EtsStatement>,
) : ComposeControlRule(decorate) {
    override fun control(call: IrCall, language: Language, scope: Scope): ComposeElement? {
        if (symbolName(call.symbol.owner) != "androidx.compose.foundation.layout.Column") return null
        target.checkArguments(call, setOf("modifier", "horizontalAlignment", "verticalArrangement", "content"))
        val child = scope.fork()
        child.semanticFlags.removeAll(setOf(UNBOUNDED_WIDTH, UNBOUNDED_HEIGHT))
        child.semanticFlags += contentFlags(argument(call, "modifier"), scope)
        val children = argument(call, "content")?.let { content(it, child) } ?: emptyList()
        val alignment = argument(call, "horizontalAlignment")?.let { language.expression(it, scope) }
            ?: target.enumValue("HorizontalAlign", "Start", call)
        val arrangementSource = argument(call, "verticalArrangement")
        val justification = arrangementSource?.let { arrangementAlignment(it, scope, target) }
        val arrangement = arrangementSource?.takeIf { justification == null }?.let { language.expression(it, scope) }
        val options = arrangement?.let { listOf(arrangementOptions(it, "Column", target, call)) } ?: emptyList()
        val attributes = listOf(target.attribute("alignItems", listOf(alignment), call)) + listOfNotNull(
            justification?.let { target.attribute("justifyContent", listOf(it), call) }) +
            if (UNBOUNDED_HEIGHT !in child.semanticFlags && hasDirectLayoutWeight(children))
                listOf(target.attribute("height", listOf(target.literal("100%", call)), call)) else emptyList()
        return ComposeElement(target.native("Column", options, call, children).copy(attributes = attributes),
            orderedArguments = listOfNotNull(arrangement, justification, alignment))
    }
}
