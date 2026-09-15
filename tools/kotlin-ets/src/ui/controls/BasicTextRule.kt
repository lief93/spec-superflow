@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.isString

internal class ComposeBasicTextRule(
    private val target: ArkUiCalls,
    decorate: (IrExpression?, Scope, ComposeElement) -> List<EtsStatement>,
) : ComposeControlRule(decorate) {
    override fun control(call: IrCall, language: Language, scope: Scope): ComposeElement? {
        if (symbolName(call.symbol.owner) != "androidx.compose.foundation.text.BasicText") return null
        target.checkArguments(call, setOf("text", "modifier", "maxLines"))
        val text = argument(call, "text") ?: target.diagnostics.unsupported(call, "BasicText requires text")
        if (!text.type.isString()) target.diagnostics.unsupported(text, "AnnotatedString BasicText is not supported")
        // Foundation BasicText uses TextStyle.Default, not Material LocalContentColor.
        val attrs = listOf(
            target.attribute("fontColor", listOf(target.literal(0xFF000000L, call)), call),
            target.attribute("fontSize", listOf(target.literal(14, call)), call),
            target.attribute("align", listOf(target.enumValue("Alignment", "TopStart", call)), call)) +
            listOfNotNull(argument(call, "maxLines")?.let {
            target.attribute("maxLines", listOf(language.expression(it, scope)), call)
        })
        return ComposeElement(target.native("Text", listOf(language.expression(text, scope)), call).copy(attributes = attrs))
    }
}
