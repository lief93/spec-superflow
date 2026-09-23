@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.expressions.*

internal data class ComposeElement(val element: EtsUiElement,
    val modifierBoundaries: Set<String> = emptySet(), val touch: TouchTargets? = null,
    val orderedArguments: List<EtsExpression> = emptyList(), val requiresBoundedSize: Boolean = false)

internal const val BOUNDED_WIDTH = "layout:bounded-width"
internal const val BOUNDED_HEIGHT = "layout:bounded-height"

internal abstract class ComposeControlRule(
    private val decorate: (IrExpression?, Scope, ComposeElement) -> List<EtsStatement>,
) : CallRule {
    final override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? = null
    final override fun lowerUi(call: IrCall, language: Language, scope: Scope): List<EtsStatement>? {
        val element = control(call, language, scope) ?: return null
        return decorate(argument(call, "modifier"), scope, element)
    }
    protected abstract fun control(call: IrCall, language: Language, scope: Scope): ComposeElement?
}
