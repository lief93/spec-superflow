@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.expressions.*

internal class ComposeRowRule(
    private val target: ArkUiCalls,
    private val content: (IrExpression, Scope) -> List<EtsStatement>,
    private val touchBoxes: MutableMap<IrCall, TouchTargets>,
    decorate: (IrExpression?, Scope, ComposeElement) -> List<EtsStatement>,
) : ComposeControlRule(decorate) {
    override fun control(call: IrCall, language: Language, scope: Scope): ComposeElement? {
        if (symbolName(call.symbol.owner) != "androidx.compose.foundation.layout.Row") return null
        target.checkArguments(call, setOf("modifier", "verticalAlignment", "horizontalArrangement", "content"))
        val touch = touchTargets(call, scope, target.diagnostics)
        if (touch != null) touchBoxes[touch.box] = touch
        val children = argument(call, "content")?.let { content(it, scope) } ?: emptyList()
        val alignment = argument(call, "verticalAlignment")?.let { language.expression(it, scope) }
            ?: target.enumValue("VerticalAlign", "Top", call)
        val attrs = mutableListOf(target.attribute("alignItems", listOf(alignment), call))
        val arrangementSource = argument(call, "horizontalArrangement")
        val justification = arrangementSource?.let { arrangementAlignment(it, scope, target) }
        val arrangement = arrangementSource?.takeIf { justification == null }?.let { language.expression(it, scope) }
        val options = arrangement?.let { listOf(arrangementOptions(it, "Row", target, call)) } ?: emptyList()
        justification?.let { attrs += target.attribute("justifyContent", listOf(it), call) }
        if (touch != null) {
            val source = language.source(call)
            attrs += target.attribute("responseRegion", listOf(touch.rowRegion(source)), call)
            val items = EtsSymbol("ui:touch:${call.startOffset}", "items", EtsNamedType("Array", listOf(EtsNamedType("TouchTestInfo"))), source)
            val dispatch = target.call("__etsNearestTouch", listOf(EtsReference(items), target.literal(touch.inset, call),
                target.literal(touch.width, call), target.literal(touch.height, call)), call,
                result = EtsNamedType("TouchResult"), identity = "compose:nearestTouch")
            attrs += target.attribute("onChildTouchTest", listOf(EtsLambda(listOf(EtsParameter(items)),
                listOf(EtsReturn(dispatch, source)), dispatch.type, source)), call)
        }
        return ComposeElement(target.native("Row", options, call, children).copy(attributes = attrs),
            orderedArguments = listOfNotNull(arrangement, justification, alignment))
    }
}
