@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.isUnit
import org.jetbrains.kotlin.ir.types.classOrNull

internal data class PointerInput(val hitTest: EtsExpression, val onTap: EtsExpression? = null)

/** An empty pointer handler still participates in sibling hit testing. */
internal class PointerInputModifier(private val target: ArkUiCalls) {
    fun value(call: IrCall, stableKey: (IrExpression) -> Boolean,
        callback: (IrExpression) -> EtsExpression): PointerInput {
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
        fun singleCall(node: IrElement?): IrCall? = when (node) {
            is IrBlockBody -> node.statements.singleOrNull()?.let(::singleCall)
            is IrReturn -> if (node.returnTargetSymbol == handler?.function?.symbol) singleCall(node.value) else null
            is IrBlock -> node.statements.singleOrNull()?.let(::singleCall)
            is IrComposite -> node.statements.singleOrNull()?.let(::singleCall)
            is IrTypeOperatorCall -> when (node.operator) {
                IrTypeOperator.IMPLICIT_CAST, IrTypeOperator.IMPLICIT_COERCION_TO_UNIT,
                IrTypeOperator.IMPLICIT_NOTNULL -> singleCall(node.argument)
                else -> null
            }
            is IrCall -> node
            else -> null
        }
        val gesture = handler?.function?.body?.let(::singleCall)
        val onTap = if (gesture != null &&
            symbolName(gesture.symbol.owner) == "androidx.compose.foundation.gestures.detectTapGestures") {
            target.checkArguments(gesture, setOf("onDoubleTap", "onLongPress", "onPress", "onTap"))
            listOf("onDoubleTap", "onLongPress", "onPress").firstOrNull { argument(gesture, it) != null }?.let {
                target.diagnostics.unsupported(argument(gesture, it)!!,
                    "pointerInput detectTapGestures currently supports onTap only")
            }
            callback(argument(gesture, "onTap")
                ?: target.diagnostics.unsupported(gesture, "pointerInput detectTapGestures requires onTap"))
        } else null
        if (handler?.function?.body?.let(::empty) != true && onTap == null)
            target.diagnostics.unsupported(call,
                "pointerInput requires an empty handler or detectTapGestures(onTap); raw pointer processing is not supported")
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
        return PointerInput(target.enumValue("HitTestMode", "Default", call), onTap)
    }
}
