@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.expressions.IrCall

internal class ComposeSnackbarHostRule(
    private val target: ArkUiCalls,
    decorate: (org.jetbrains.kotlin.ir.expressions.IrExpression?, Scope, ComposeElement) -> List<EtsStatement>,
) : ComposeControlRule(decorate) {
    override fun control(call: IrCall, language: Language, scope: Scope): ComposeElement? {
        if (symbolName(call.symbol.owner) != "androidx.compose.material3.SnackbarHost") return null
        target.checkArguments(call, setOf("hostState", "modifier"))
        val stateSource = argument(call, "hostState")
            ?: target.diagnostics.unsupported(call, "SnackbarHost requires hostState")
        val state = language.expression(stateSource, scope)
        if (state.type != snackbarHostStateType)
            target.diagnostics.unsupported(stateSource, "SnackbarHost requires mapped SnackbarHostState")
        return ComposeElement(target.native("Stack", listOf(target.stackOptions(call)), call, emptyList()),
            orderedArguments = listOf(state))
    }
}
