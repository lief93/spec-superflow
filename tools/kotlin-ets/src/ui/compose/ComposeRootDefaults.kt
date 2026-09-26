@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.compose

import dev.ets.symbolName
import org.jetbrains.kotlin.ir.expressions.IrBlock
import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.expressions.IrComposite
import org.jetbrains.kotlin.ir.expressions.IrExpression
import org.jetbrains.kotlin.ir.expressions.IrTypeOperatorCall
import org.jetbrains.kotlin.ir.expressions.IrGetObjectValue

/** Defaults whose identity/lifecycle belongs to a Compose composition host. */
fun composeHostProvidedRootDefault(expression: IrExpression?): Boolean {
    if (expression == null) return false
    val owned = setOf(
        "androidx.compose.runtime.remember",
        "androidx.compose.runtime.saveable.rememberSaveable",
        "androidx.compose.runtime.rememberCoroutineScope",
    )
    fun rootCall(value: IrExpression): IrCall? = when (value) {
        is IrCall -> value
        is IrTypeOperatorCall -> rootCall(value.argument)
        is IrBlock -> (value.statements.lastOrNull() as? IrExpression)?.let(::rootCall)
        is IrComposite -> (value.statements.lastOrNull() as? IrExpression)?.let(::rootCall)
        else -> null
    }
    return rootCall(expression)?.let { symbolName(it.symbol.owner) in owned } == true
}

/** Compose's identity Modifier is a framework parameter, not a target runtime value. */
fun composeEmptyModifierDefault(expression: IrExpression?): Boolean {
    fun value(current: IrExpression): IrExpression = when (current) {
        is IrTypeOperatorCall -> value(current.argument)
        is IrBlock -> (current.statements.lastOrNull() as? IrExpression)?.let(::value) ?: current
        is IrComposite -> (current.statements.lastOrNull() as? IrExpression)?.let(::value) ?: current
        else -> current
    }
    val resolved = expression?.let(::value) as? IrGetObjectValue ?: return false
    return symbolName(resolved.symbol.owner) == "androidx.compose.ui.Modifier.Companion"
}
