@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.expressions.*

/**
 * Material3 OutlinedTextFieldDefaults.DecorationBox / ContainerBox have no loaded IR.
 * Map the source slots onto native Column/Row/Stack; do not invent live IME/indication.
 */
internal class ComposeTextFieldDecorationRule(
    private val target: ArkUiCalls,
    private val content: (IrExpression, Scope) -> List<EtsStatement>,
    decorate: (IrExpression?, Scope, ComposeElement) -> List<EtsStatement>,
) : ComposeControlRule(decorate) {
    override fun control(call: IrCall, language: Language, scope: Scope): ComposeElement? {
        val api = symbolName(call.symbol.owner)
        return when (api) {
            "androidx.compose.material3.OutlinedTextFieldDefaults.DecorationBox" -> decoration(call, language, scope)
            "androidx.compose.material3.OutlinedTextFieldDefaults.ContainerBox" -> container(call, language, scope)
            else -> null
        }
    }

    private fun decoration(call: IrCall, language: Language, scope: Scope): ComposeElement {
        target.checkArguments(call, setOf("value", "innerTextField", "enabled", "singleLine",
            "visualTransformation", "interactionSource", "isError", "label", "placeholder",
            "leadingIcon", "trailingIcon", "supportingText", "colors", "contentPadding", "container"))
        argument(call, "value")?.let { language.expression(it, scope) }
        argument(call, "enabled")?.let { language.expression(it, scope) }
        argument(call, "singleLine")?.let { language.expression(it, scope) }
        argument(call, "visualTransformation")?.let { language.expression(it, scope) }
        argument(call, "interactionSource")?.let { language.expression(it, scope) }
        argument(call, "isError")?.let { language.expression(it, scope) }
        argument(call, "colors")?.let { language.expression(it, scope) }
        val inner = argument(call, "innerTextField")
            ?: target.diagnostics.unsupported(call, "DecorationBox requires innerTextField")
        val padding = argument(call, "contentPadding")?.let { language.expression(it, scope) }
        val field = slot(inner, scope)
        val leading = argument(call, "leadingIcon")?.let { slot(it, scope) }.orEmpty()
        val trailing = argument(call, "trailingIcon")?.let { slot(it, scope) }.orEmpty()
        val placeholder = argument(call, "placeholder")?.let { slot(it, scope) }.orEmpty()
        val label = argument(call, "label")?.let { slot(it, scope) }.orEmpty()
        val supporting = argument(call, "supportingText")?.let { slot(it, scope) }.orEmpty()
        val container = argument(call, "container")?.let { slot(it, scope) }.orEmpty()
        val input = if (placeholder.isEmpty()) field else listOf(
            target.native("Stack", listOf(target.stackOptions(call)), call, placeholder + field))
        val row = target.native("Row", emptyList(), call, leading + input + trailing).copy(attributes = listOf(
            target.attribute("alignItems", listOf(target.enumValue("VerticalAlign", "Center", call)), call)) +
            listOfNotNull(padding?.let { target.attribute("padding", listOf(it), call) }))
        val body = target.native("Column", emptyList(), call, label + listOf(row) + supporting)
        val root = if (container.isEmpty()) body
        else target.native("Stack", listOf(target.stackOptions(call)), call, container + listOf(body))
        return ComposeElement(root, setOf("padding", "backgroundColor", "onClick", "enabled"))
    }

    private fun container(call: IrCall, language: Language, scope: Scope): ComposeElement {
        target.checkArguments(call, setOf("enabled", "isError", "interactionSource", "colors", "shape"))
        argument(call, "enabled")?.let { language.expression(it, scope) }
        argument(call, "interactionSource")?.let { language.expression(it, scope) }
        argument(call, "colors")?.let { language.expression(it, scope) }
        argument(call, "isError")?.let { language.expression(it, scope) }
        val shape = argument(call, "shape")?.let { language.expression(it, scope) }
        val attrs = buildList {
            add(target.attribute("width", listOf(target.literal("100%", call)), call))
            add(target.attribute("height", listOf(target.literal("100%", call)), call))
            shape?.let { add(target.attribute("borderRadius", listOf(it), call)) }
        }
        return ComposeElement(target.native("Stack", listOf(target.stackOptions(call)), call).copy(attributes = attrs),
            setOf("padding", "backgroundColor", "onClick", "enabled"),
            orderedArguments = listOfNotNull(shape))
    }

    private fun slot(expression: IrExpression, scope: Scope): List<EtsStatement> {
        val resolved = resolveExpression(expression, scope)
        if (resolved is IrConst && resolved.kind == IrConstKind.Null) return emptyList()
        return content(expression, scope)
    }
}
