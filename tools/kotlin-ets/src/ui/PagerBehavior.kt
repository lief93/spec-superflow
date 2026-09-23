@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.expressions.IrExpression
import org.jetbrains.kotlin.ir.expressions.IrGetField
import org.jetbrains.kotlin.ir.expressions.IrGetObjectValue
import org.jetbrains.kotlin.ir.expressions.IrGetValue

/** Normalizes Compose pager behavior that ArkUI Swiper already provides natively. */
internal fun validatePagerBehavior(call: IrCall, scope: Scope, diagnostics: DiagnosticSink) {
    argument(call, "flingBehavior")?.let { fling ->
        val resolved = resolveExpression(fling, scope) as? IrCall
            ?: diagnostics.unsupported(fling, "HorizontalPager requires PagerDefaults.flingBehavior")
        if (symbolName(resolved.symbol.owner) != "androidx.compose.foundation.pager.PagerDefaults.flingBehavior")
            diagnostics.unsupported(fling, "HorizontalPager custom flingBehavior has no ArkUI Swiper equivalent")
        val sourceState = argument(call, "state")
        val flingState = argument(resolved, "state")
        if (sourceState == null || flingState == null || !sameSourceValue(sourceState, flingState, scope))
            diagnostics.unsupported(fling,
                "PagerDefaults.flingBehavior must use the same PagerState as HorizontalPager")
        resolved.symbol.owner.valueParameters.forEachIndexed { index, parameter ->
            if (resolved.getValueArgument(index) != null && parameter.name.asString() != "state")
                diagnostics.unsupported(fling,
                    "HorizontalPager custom fling parameter is not represented by ArkUI Swiper: ${parameter.name}")
        }
    }
    argument(call, "snapPosition")?.let { snap ->
        if (pagerSnapPosition(snap, scope) != "Center")
            diagnostics.unsupported(snap,
                "HorizontalPager currently requires SnapPosition.Center for ArkUI Swiper")
    }
}

private fun sameSourceValue(left: IrExpression, right: IrExpression, scope: Scope): Boolean {
    if (left is IrGetValue && right is IrGetValue && left.symbol == right.symbol) return true
    return resolveExpression(left, scope) === resolveExpression(right, scope)
}

private fun pagerSnapPosition(expression: IrExpression, scope: Scope): String? {
    val resolved = resolveExpression(expression, scope) ?: return null
    val (owner, name) = when (resolved) {
        is IrCall -> {
            val function = resolved.symbol.owner
            val property = function.correspondingPropertySymbol?.owner
            (property?.let(::symbolName) ?: symbolName(function)) to
                (property?.name?.asString() ?: getterName(function.name.asString()))
        }
        is IrGetField -> {
            val field = resolved.symbol.owner
            val property = field.correspondingPropertySymbol?.owner
            (property?.let(::symbolName) ?: symbolName(field)) to
                (property?.name?.asString() ?: field.name.asString())
        }
        is IrGetObjectValue -> symbolName(resolved.symbol.owner) to resolved.symbol.owner.name.asString()
        else -> return null
    }
    return name.takeIf { it == "Center" && owner.contains("SnapPosition") }
}

private fun getterName(name: String): String = when {
    name.startsWith("<get-") && name.endsWith(">") -> name.removePrefix("<get-").removeSuffix(">")
    name.startsWith("get") -> name.removePrefix("get")
    else -> name
}
