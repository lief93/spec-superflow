@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.expressions.IrCall

internal data class WrapContent(val width: Boolean, val height: Boolean, val alignment: EtsExpression)

internal fun wrapContent(call: IrCall, language: Language, scope: Scope, target: ArkUiCalls): WrapContent? {
    val axes = when (symbolName(call.symbol.owner)) {
        "androidx.compose.foundation.layout.wrapContentWidth" -> true to false
        "androidx.compose.foundation.layout.wrapContentHeight" -> false to true
        "androidx.compose.foundation.layout.wrapContentSize" -> true to true
        else -> return null
    }
    target.checkArguments(call, setOf("align", "unbounded"))
    val unbounded = argument(call, "unbounded")
    if (unbounded != null) when ((language.expression(unbounded, scope) as? EtsLiteral)?.value) {
        false -> Unit
        true -> target.diagnostics.omitUi(unbounded,
            "wrapContent unbounded measurement has no native ArkUI equivalent",
            "androidx.compose.foundation.layout.wrapContent:unbounded",
            "platform_capability_fallback",
            "Wrapping and alignment are retained, but infinite child constraints use native wrap-content measurement.")
        else -> target.diagnostics.unsupported(unbounded,
            "wrapContent unbounded requires a constant Boolean to preserve measurement semantics")
    }
    val supplied = argument(call, "align")?.let { language.expression(it, scope) }
    if (supplied != null) {
        val expected = if (axes.first && axes.second) "Alignment" else if (axes.second) "VerticalAlign" else "HorizontalAlign"
        if ((supplied as? EtsMember)?.receiver.let { it as? EtsReference }?.symbol?.id != "arkui:$expected")
            target.diagnostics.unsupported(call, "wrapContent alignment requires a resolved enum value to preserve evaluation order")
    }
    val alignment = if (axes.first && axes.second) supplied ?: target.enumValue("Alignment", "Center", call)
    else {
        val vertical = axes.second
        val default = target.enumValue("Alignment", if (vertical) "Start" else "Top", call)
        if (supplied == null) default else {
            // Restrict to resolved enum values so evaluating alignment cannot be duplicated.
            val name = (supplied as? EtsMember)?.takeIf { it.receiver is EtsReference }?.name
                ?: target.diagnostics.unsupported(call, "wrapContent axis alignment requires a resolved enum value")
            val mapped = if (vertical) mapOf("Top" to "TopStart", "Center" to "Start", "Bottom" to "BottomStart")
                else mapOf("Start" to "TopStart", "Center" to "Top", "End" to "TopEnd")
            target.enumValue("Alignment", mapped[name] ?: target.diagnostics.unsupported(call, "Unsupported wrapContent alignment"), call)
        }
    }
    return WrapContent(axes.first, axes.second, alignment)
}
