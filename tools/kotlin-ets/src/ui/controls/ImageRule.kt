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
        val scale = argument(call, "contentScale")?.let { imageScale(it, scope, target) } ?: "Contain"
        attrs += target.attribute("objectFit", listOf(target.enumValue("ImageFit", scale, call)), call)
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

internal fun imageScale(value: IrExpression, scope: Scope, target: ArkUiCalls): String {
    if (value is IrGetValue) scope.aliases[value.symbol]?.let { return imageScale(it, scope, target) }
    val property = (value as? IrCall)?.symbol?.owner?.correspondingPropertySymbol?.owner?.let(::symbolName)
    val scales = mapOf("Fit" to "Contain", "Crop" to "Cover", "FillBounds" to "Fill", "Inside" to "ScaleDown", "None" to "None")
    return scales.entries.firstOrNull { property == "androidx.compose.ui.layout.ContentScale.Companion.${it.key}" }?.value
        ?: target.diagnostics.unsupported(value, "Unsupported ContentScale; expected Fit, Crop, FillBounds, Inside or None")
}
