@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.expressions.*

/** Native Scroll owns the offset when the source only requests a default scroll state. */
internal class ScrollModifier(
    private val target: ArkUiCalls,
    private val language: Language,
) {
    fun validateState(state: IrCall, scope: Scope) {
        target.checkArguments(state, setOf("initial"))
        val initial = argument(state, "initial")?.let { language.expression(it, scope) }
        if (initial != null && (initial as? EtsLiteral)?.value != 0)
            target.diagnostics.unsupported(state, "Native scroll currently requires a zero initial offset")
    }

    fun axis(call: IrCall): String? = when (symbolName(call.symbol.owner)) {
        "androidx.compose.foundation.verticalScroll" -> "height"
        "androidx.compose.foundation.horizontalScroll" -> "width"
        else -> null
    }

    fun attributes(call: IrCall, scope: Scope): List<EtsCall> {
        target.checkArguments(call, setOf("state", "enabled", "reverseScrolling"))
        fun resolve(value: IrExpression?): IrExpression? =
            if (value is IrGetValue && value.symbol in scope.aliases) resolve(scope.aliases[value.symbol]) else value
        val state = resolve(argument(call, "state")) as? IrCall
        if (state == null || symbolName(state.symbol.owner) != "androidx.compose.foundation.rememberScrollState")
            target.diagnostics.unsupported(call, "Scroll requires a local rememberScrollState; shared or external state is not yet supported")
        validateState(state, scope)
        val reverse = argument(call, "reverseScrolling")?.let { language.expression(it, scope) }
        if (reverse != null && (reverse as? EtsLiteral)?.value != false)
            target.diagnostics.unsupported(call, "Unsupported scroll reverseScrolling; reverse layout must be mapped explicitly")
        val enabled = argument(call, "enabled")?.let { language.expression(it, scope) } ?: target.literal(true, call)
        return listOf(
            target.attribute("scrollable", listOf(target.enumValue("ScrollDirection", if (axis(call) == "height") "Vertical" else "Horizontal", call)), call),
            target.attribute("scrollBar", listOf(target.enumValue("BarState", "Off", call)), call),
            target.attribute("enableScrollInteraction", listOf(enabled), call),
            target.attribute("align", listOf(target.enumValue("Alignment", "TopStart", call)), call),
        )
    }
}
