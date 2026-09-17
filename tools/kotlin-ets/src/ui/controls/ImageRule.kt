@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.expressions.*

internal class ComposeImageRule(
    private val target: ArkUiCalls,
    decorate: (IrExpression?, Scope, ComposeElement) -> List<EtsStatement>,
) : ComposeControlRule(decorate) {
    override fun control(call: IrCall, language: Language, scope: Scope): ComposeElement? {
        if (symbolName(call.symbol.owner) != "androidx.compose.foundation.Image") return null
        target.checkArguments(call, setOf("painter", "contentDescription", "modifier", "contentScale", "alpha"))
        val painter = argument(call, "painter") ?: target.diagnostics.unsupported(call, "Image requires supported Painter overload")
        val attrs = imageDescription(call, language, scope, target).toMutableList()
        val scale = argument(call, "contentScale")?.let { language.expression(it, scope) } ?: target.enumValue("ImageFit", "Contain", call)
        attrs += target.attribute("objectFit", listOf(scale), call)
        argument(call, "alpha")?.let { attrs += target.attribute("opacity", listOf(language.expression(it, scope)), call) }
        return ComposeElement(target.native("Image", listOf(language.expression(painter, scope)), call).copy(attributes = attrs))
    }
}

internal fun imageDescription(call: IrCall, language: Language, scope: Scope, target: ArkUiCalls): List<EtsCall> {
    val source = argument(call, "contentDescription") ?: target.diagnostics.unsupported(call, "Image requires contentDescription")
    val description = language.expression(source, scope)
    return if (description is EtsLiteral && description.value == null)
        listOf(target.attribute("accessibilityLevel", listOf(target.literal("no", call)), call))
    else {
        if (description.type != EtsTypes.STRING) target.diagnostics.unsupported(source, "Nullable image description requires an explicit non-null branch")
        listOf(target.attribute("accessibilityText", listOf(description), call))
    }
}
