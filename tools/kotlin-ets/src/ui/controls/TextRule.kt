@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.isString

internal class ComposeTextRule(
    private val target: ArkUiCalls,
    private val dimension: (IrExpression, Scope, String) -> EtsExpression,
    private val useMaterialTypography: () -> Unit,
    decorate: (IrExpression?, Scope, ComposeElement) -> List<EtsStatement>,
) : ComposeControlRule(decorate) {
    override fun control(call: IrCall, language: Language, scope: Scope): ComposeElement? {
        val api = symbolName(call.symbol.owner)
        if (api !in setOf("androidx.compose.material3.Text", "androidx.compose.material.Text")) return null
        target.checkArguments(call, setOf("text", "modifier", "minLines") + textStyleArgumentOrder,
            setOf("softWrap"))
        val text = argument(call, "text") ?: target.diagnostics.unsupported(call, "Text requires text")
        if (!text.type.isString()) target.diagnostics.unsupported(text, "AnnotatedString Text is not supported")
        val styleArgument = argument(call, "style")
        if (LINE_HEIGHT_STYLE_CONTEXT in scope.semanticFlags ||
            styleArgument?.let { hasUnsupportedLineHeightStyle(it, scope) } == true) {
            target.diagnostics.omitUi(call,
                "LineHeightStyle is retained as typed metadata, but Harmony Text can only represent Center/None/Fixed through halfLeading; unsupported alignment, trim, or mode is not emulated",
                "compose.text.line_height_style", "line_height_style_fallback",
                "Numeric lineHeight is preserved; unsupported line-height distribution or first/last-line trimming may render differently",
                discarded = emptyList())
        }
        val ambient = scope.ambientValues[MATERIAL_CONTEXT]?.takeIf { api == "androidx.compose.material3.Text" }
        val at = language.source(call)
        fun fallbackColor() = ambient?.let { materialContentColor(it, at) } ?: target.literal(0xFF000000L, call)
        if (ambient != null || argument(call, "minLines") != null ||
            (textStyleArgumentOrder - setOf("color", "fontSize")).any { argument(call, it) != null }) {
            if (api == "androidx.compose.material.Text" && argument(call, "style") == null)
                target.diagnostics.unsupported(call, "Material 2 LocalTextStyle requires an explicit style")
            val inherited = if (api == "androidx.compose.material3.Text")
                ambient?.let { materialCurrentTextStyle(it, at) } ?: defaultTypographyRole("bodyLarge", at)
            else EtsNew(textStyleType, textStyleFields.keys.map { EtsLiteral(null, EtsTypes.NULL, at) }, at)
            val style = argument(call, "style")?.let { value ->
                val provided = language.expression(value, scope)
                if (api == "androidx.compose.material3.Text") mergeTextStyles(inherited, provided, at) else provided
            } ?: inherited
            val values = textStyleArgumentOrder.map { name ->
                if (name == "style") style else argument(call, name)?.let { language.expression(it, scope) }
                    ?: when (name) {
                    "overflow" -> target.enumValue("TextOverflow", "Clip", call)
                    "maxLines" -> target.literal(Int.MAX_VALUE, call)
                    else -> EtsLiteral(null, EtsTypes.NULL, at)
                }
            }
            val modifier = textStyleModifier(values + fallbackColor(), at)
            val attributes = listOf(target.attribute("align", listOf(target.enumValue("Alignment", "TopStart", call)), call),
                target.attribute("attributeModifier", listOf(modifier), call)) +
                minLinesConstraint(call, style, language, scope)
            return ComposeElement(target.native("Text", listOf(language.expression(text, scope)), call).copy(attributes = attributes),
                orderedArguments = listOf(modifier))
        }
        val attrs = buildList {
            add(target.attribute("align", listOf(target.enumValue("Alignment", "TopStart", call)), call))
            argument(call, "color")?.let { value -> add(target.attribute("fontColor", listOf(
                resolveComposeColor(language.expression(value, scope), fallbackColor(), language.source(value))), call)) }
                ?: scope.ambientValues[MATERIAL_CONTEXT]?.takeIf { api == "androidx.compose.material3.Text" }?.let {
                    add(target.attribute("fontColor", listOf(materialContentColor(it, language.source(call))), call))
                }
            val size = argument(call, "fontSize")?.let { dimension(it, scope, "sp") }
            if (api == "androidx.compose.material3.Text") {
                useMaterialTypography()
                add(target.attribute("attributeModifier", listOf(EtsNew(
                    EtsNamedType("__etsMaterialTypography", symbolId = "compose:materialTypography", external = true),
                    listOf(size ?: target.literal(16, call), target.literal(24, call),
                        target.literal(400, call), target.literal(0.5, call)), language.source(call))), call))
            } else if (size != null) add(target.attribute("fontSize", listOf(size), call))
        }
        return ComposeElement(target.native("Text", listOf(language.expression(text, scope)), call).copy(attributes = attrs),
            if (api == "androidx.compose.material3.Text") setOf("padding") else emptySet())
    }

    private fun minLinesConstraint(call: IrCall, style: EtsExpression, language: Language,
        scope: Scope): List<EtsCall> {
        val minLinesSource = argument(call, "minLines") ?: return emptyList()
        val at = language.source(minLinesSource)
        val minLines = language.expression(minLinesSource, scope)
        if (minLines.type != EtsTypes.NUMBER)
            target.diagnostics.unsupported(minLinesSource, "Text minLines requires Int")
        val styleLineHeight = EtsMember(style, "lineHeight", EtsNullableType(EtsTypes.NUMBER), at)
        val styleFontSize = EtsMember(style, "fontSize", EtsNullableType(EtsTypes.NUMBER), at)
        val fallbackLineHeight = EtsBinary("*", EtsBinary("??", styleFontSize,
            target.literal(14, minLinesSource), EtsTypes.NUMBER, at), target.literal(1.2, minLinesSource),
            EtsTypes.NUMBER, at)
        val lineHeight = EtsBinary("??", styleLineHeight, fallbackLineHeight, EtsTypes.NUMBER, at)
        val minHeight = EtsBinary("*", lineHeight, minLines, EtsTypes.NUMBER, at)
        return listOf(target.attribute("constraintSize", listOf(target.record("ConstraintSizeOptions",
            linkedMapOf("minHeight" to minHeight), minLinesSource)), call))
    }
}
