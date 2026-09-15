@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.isString

internal class ComposeTextRule(
    private val target: ArkUiCalls,
    private val color: (IrExpression, Scope) -> EtsExpression,
    private val dimension: (IrExpression, Scope, String) -> EtsExpression,
    private val typography: () -> MaterialTextContext,
    decorate: (IrExpression?, Scope, ComposeElement) -> List<EtsStatement>,
) : ComposeControlRule(decorate) {
    override fun control(call: IrCall, language: Language, scope: Scope): ComposeElement? {
        val api = symbolName(call.symbol.owner)
        if (api !in setOf("androidx.compose.material3.Text", "androidx.compose.material.Text")) return null
        target.checkArguments(call, setOf("text", "modifier", "color", "fontSize"))
        val text = argument(call, "text") ?: target.diagnostics.unsupported(call, "Text requires text")
        if (!text.type.isString()) target.diagnostics.unsupported(text, "AnnotatedString Text is not supported")
        val attrs = buildList {
            add(target.attribute("align", listOf(target.enumValue("Alignment", "TopStart", call)), call))
            argument(call, "color")?.let { add(target.attribute("fontColor", listOf(color(it, scope)), call)) }
                ?: scope.ambientValues[MATERIAL_CONTEXT]?.takeIf { api == "androidx.compose.material3.Text" }?.let {
                    add(target.attribute("fontColor", listOf(materialContentColor(it, language.source(call))), call))
                }
            val size = argument(call, "fontSize")?.let { dimension(it, scope, "sp") }
            if (api == "androidx.compose.material3.Text") {
                val context = typography()
                add(target.attribute("attributeModifier", listOf(EtsNew(
                    EtsNamedType("__etsMaterialTypography", symbolId = "compose:materialTypography", external = true),
                    listOf(size ?: target.literal(context.size, call), target.literal(context.lineHeight, call),
                        target.literal(context.weight, call), target.literal(context.tracking, call)), language.source(call))), call))
            } else if (size != null) add(target.attribute("fontSize", listOf(size), call))
        }
        return ComposeElement(target.native("Text", listOf(language.expression(text, scope)), call).copy(attributes = attrs),
            if (api == "androidx.compose.material3.Text") setOf("padding") else emptySet())
    }
}
