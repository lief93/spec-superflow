@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.expressions.IrExpression

internal class ComposeTopAppBarRule(
    private val target: ArkUiCalls,
    private val content: (IrExpression, Scope) -> List<EtsStatement>,
    private val dimension: (IrExpression, Scope, String) -> EtsExpression,
    private val decorate: (IrExpression?, Scope, ComposeElement) -> List<EtsStatement>,
) : CallRule {
    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? = null

    override fun lowerUi(call: IrCall, language: Language, scope: Scope): List<EtsStatement>? {
        if (symbolName(call.symbol.owner) != "androidx.compose.material3.TopAppBar") return null
        target.checkArguments(call, setOf("title", "modifier", "navigationIcon", "actions", "expandedHeight"))
        val title = argument(call, "title") ?: target.diagnostics.unsupported(call, "TopAppBar requires title content")
        val at = language.source(call)
        val parent = materialContext(scope, at)
        val scheme = materialScheme(parent, at)
        val height = argument(call, "expandedHeight")?.let { dimension(it, scope, "dp") }
            ?: target.literal(64, call)

        fun slot(body: IrExpression, color: EtsExpression, style: EtsExpression): List<EtsStatement> {
            val child = scope.fork()
            child.ambientValues[MATERIAL_CONTEXT] = newMaterialContext(at,
                MaterialContextField.COLOR_SCHEME to scheme,
                MaterialContextField.CONTENT_COLOR to color,
                MaterialContextField.TYPOGRAPHY to materialTypography(parent, at),
                MaterialContextField.TEXT_STYLE to style,
                MaterialContextField.SHAPES to materialShapes(parent, at))
            return content(body, child)
        }

        val onSurface = EtsMember(scheme, "onSurface", EtsTypes.NUMBER, at)
        val onSurfaceVariant = EtsMember(scheme, "onSurfaceVariant", EtsTypes.NUMBER, at)
        val titleStyle = EtsMember(materialTypography(parent, at), "titleLarge", textStyleType, at)
        val inheritedStyle = materialCurrentTextStyle(parent, at)
        val children = mutableListOf<EtsStatement>()
        argument(call, "navigationIcon")?.let { navigation ->
            children += target.native("Row", emptyList(), call, slot(navigation, onSurface, inheritedStyle)).copy(attributes = listOf(
                target.attribute("alignItems", listOf(target.enumValue("VerticalAlign", "Center", call)), call)))
        }
        children += target.native("Stack", listOf(target.stackOptions(call)), call,
            slot(title, onSurface, titleStyle)).copy(attributes = listOf(
                target.attribute("layoutWeight", listOf(target.literal(1, call)), call),
                target.attribute("height", listOf(height), call),
                target.attribute("alignContent", listOf(target.enumValue("Alignment", "CenterStart", call)), call)))
        argument(call, "actions")?.let { actions ->
            children += target.native("Row", emptyList(), call, slot(actions, onSurfaceVariant, inheritedStyle)).copy(attributes = listOf(
                target.attribute("alignItems", listOf(target.enumValue("VerticalAlign", "Center", call)), call)))
        }
        val bar = target.native("Row", emptyList(), call, children).copy(attributes = listOf(
            target.attribute("height", listOf(height), call),
            target.attribute("alignItems", listOf(target.enumValue("VerticalAlign", "Center", call)), call),
            target.attribute("backgroundColor", listOf(EtsMember(scheme, "surface", EtsTypes.NUMBER, at)), call)))
        return decorate(argument(call, "modifier"), scope, ComposeElement(bar,
            modifierBoundaries = setOf("backgroundColor"), orderedArguments = listOf(height)))
    }
}
