@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.isUnit
import org.jetbrains.kotlin.ir.types.classOrNull

/** An empty pointer handler still participates in sibling hit testing. */
internal class PointerInputModifier(private val target: ArkUiCalls) {
    fun value(call: IrCall, stableKey: (IrExpression) -> Boolean): EtsExpression {
        target.checkArguments(call, setOf("key1", "key2", "keys", "block"))
        val block = argument(call, "block")
        val unwrapped = if (block is IrTypeOperatorCall && block.operator == IrTypeOperator.SAM_CONVERSION &&
            block.typeOperand.classOrNull?.owner?.let(::symbolName) == "androidx.compose.ui.input.pointer.PointerInputEventHandler")
            block.argument else block
        val handler = unwrapped as? IrFunctionExpression
        fun empty(node: IrElement): Boolean = when (node) {
            is IrBlockBody -> node.statements.all(::empty)
            is IrReturn -> node.returnTargetSymbol == handler?.function?.symbol && empty(node.value)
            is IrGetObjectValue -> node.type.isUnit()
            else -> false
        }
        if (handler?.function?.body?.let(::empty) != true)
            target.diagnostics.unsupported(call, "pointerInput currently requires an empty handler; gesture/event processing needs an explicit mapping")
        fun key(value: IrExpression): Boolean = when (value) {
            is IrVararg -> value.elements.all { it is IrExpression && key(it) }
            is IrGetObjectValue -> value.type.isUnit()
            else -> stableKey(value)
        }
        for (name in listOf("key1", "key2", "keys")) {
            val value = argument(call, name) ?: continue
            if (!key(value)) target.diagnostics.unsupported(value,
                "pointerInput with an empty handler requires effect-free keys")
        }
        // Default blocks lower siblings without blocking descendants or ancestors.
        return target.enumValue("HitTestMode", "Default", call)
    }
}
