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
        target.checkArguments(call, setOf("text", "modifier") + textStyleArgumentOrder)
        val text = argument(call, "text") ?: target.diagnostics.unsupported(call, "Text requires text")
        if (!text.type.isString()) target.diagnostics.unsupported(text, "AnnotatedString Text is not supported")
        if ((textStyleArgumentOrder - setOf("color", "fontSize")).any { argument(call, it) != null }) {
            if (api == "androidx.compose.material.Text" && argument(call, "style") == null)
                target.diagnostics.unsupported(call, "Material 2 LocalTextStyle requires an explicit style")
            val at = language.source(call)
            val context = typography()
            val defaultFields = if (api == "androidx.compose.material3.Text") mapOf("fontSize" to context.size,
                "fontWeight" to context.weight, "lineHeight" to context.lineHeight, "letterSpacing" to context.tracking) else emptyMap()
            val values = textStyleArgumentOrder.map { name -> argument(call, name)?.let { language.expression(it, scope) }
                ?: when (name) {
                    "style" -> EtsNew(textStyleType, textStyleFields.keys.map { field ->
                        defaultFields[field]?.let { EtsLiteral(it, EtsTypes.NUMBER, at) } ?: EtsLiteral(null, EtsTypes.NULL, at)
                    }, at)
                    "overflow" -> target.enumValue("TextOverflow", "Clip", call)
                    "maxLines" -> target.literal(Int.MAX_VALUE, call)
                    else -> EtsLiteral(null, EtsTypes.NULL, at)
                }
            }
            val fallback = scope.ambientValues[MATERIAL_CONTEXT]?.takeIf { api == "androidx.compose.material3.Text" }
                ?.let { materialContentColor(it, at) } ?: target.literal(0xFF000000L, call)
            val modifier = textStyleModifier(values + fallback, at)
            val attributes = listOf(target.attribute("align", listOf(target.enumValue("Alignment", "TopStart", call)), call),
                target.attribute("attributeModifier", listOf(modifier), call))
            return ComposeElement(target.native("Text", listOf(language.expression(text, scope)), call).copy(attributes = attributes),
                orderedArguments = listOf(modifier))
        }
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
