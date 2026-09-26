@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.compose

import dev.ets.*
import dev.ets.widgets.*
import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.expressions.IrExpression

/** Optional project/framework extension that still targets the neutral widget model. */
interface ComposeWidgetAdapterModule {
    fun createWidgetRule(): ComposeWidgetRule
}

fun interface ComposeWidgetRule {
    fun lower(call: IrCall, language: Language, scope: Scope,
        services: ComposeWidgetServices): Widget<EtsExpression, SourceSpan>?
}

/** Shared source semantics exposed to widget rules; no ArkUI nodes or source-text emission. */
interface ComposeWidgetServices {
    fun content(expression: IrExpression, scope: Scope,
        parent: WidgetLayoutScope?,
        arguments: List<EtsExpression> = emptyList()): Children<EtsExpression, SourceSpan>
    val parent: WidgetLayoutScope?
    fun modifiers(expression: IrExpression?, scope: Scope,
        parent: WidgetLayoutScope?): List<WidgetModifier<EtsExpression, SourceSpan>>
    fun value(expression: IrExpression, scope: Scope,
        type: WidgetValueType): WidgetValue<EtsExpression, SourceSpan>
}
