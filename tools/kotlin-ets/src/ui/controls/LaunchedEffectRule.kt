@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.expressions.IrGetObjectValue

/** Constant-key effects enter with their conditional UI branch on ArkUI. */
internal class ComposeLaunchedEffectRule(
    private val target: ArkUiCalls,
    private val callback: (org.jetbrains.kotlin.ir.expressions.IrExpression, Scope) -> EtsExpression,
) : CallRule {
    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? = null

    override fun lowerUi(call: IrCall, language: Language, scope: Scope): List<EtsStatement>? {
        if (symbolName(call.symbol.owner) != "androidx.compose.runtime.LaunchedEffect") return null
        val supplied = call.symbol.owner.valueParameters.mapIndexedNotNull { index, parameter ->
            call.getValueArgument(index)?.let { parameter.name.asString() to it }
        }
        val block = supplied.singleOrNull { it.first == "block" }?.second
            ?: target.diagnostics.unsupported(call, "LaunchedEffect requires a source block")
        val keys = supplied.filterNot { it.first == "block" }.map { it.second }
        if (keys.size != 1 || (keys.single() as? IrGetObjectValue)?.symbol?.owner?.let(::symbolName) != "kotlin.Unit")
            target.diagnostics.unsupported(call, "LaunchedEffect currently requires the constant Unit key")
        val effect = callback(block, scope)
        val zero = target.literal(0, call)
        return listOf(target.native("Blank", emptyList(), call).copy(attributes = listOf(
            target.attribute("width", listOf(zero), call),
            target.attribute("height", listOf(zero), call),
            target.attribute("onAppear", listOf(effect), call))))
    }
}
