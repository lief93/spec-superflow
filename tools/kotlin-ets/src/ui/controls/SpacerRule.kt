@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.expressions.*

internal class ComposeSpacerRule(
    private val target: ArkUiCalls,
    decorate: (IrExpression?, Scope, ComposeElement) -> List<EtsStatement>,
) : ComposeControlRule(decorate) {
    override fun control(call: IrCall, language: Language, scope: Scope): ComposeElement? {
        if (symbolName(call.symbol.owner) != "androidx.compose.foundation.layout.Spacer") return null
        target.checkArguments(call, setOf("modifier"))
        return ComposeElement(target.native("Row", emptyList(), call, emptyList()))
    }
}
