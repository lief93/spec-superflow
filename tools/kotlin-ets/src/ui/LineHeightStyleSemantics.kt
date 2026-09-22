@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.classOrNull
import java.util.Collections
import java.util.IdentityHashMap

internal const val LINE_HEIGHT_STYLE_CONTEXT = "compose.text.lineHeightStyle"

private enum class LineHeightMetadata { NONE, REPRESENTABLE, UNSUPPORTED }
private data class LineHeightSemantic(val alignment: String, val trim: String, val mode: String)

internal fun hasUnsupportedLineHeightStyle(expression: IrExpression, scope: Scope): Boolean {
    val traversed = Collections.newSetFromMap(IdentityHashMap<IrElement, Boolean>())
    val semanticVisited = Collections.newSetFromMap(IdentityHashMap<IrElement, Boolean>())
    val constantVisited = Collections.newSetFromMap(IdentityHashMap<IrElement, Boolean>())

    fun combine(values: List<LineHeightMetadata>): LineHeightMetadata = when {
        LineHeightMetadata.UNSUPPORTED in values -> LineHeightMetadata.UNSUPPORTED
        LineHeightMetadata.REPRESENTABLE in values -> LineHeightMetadata.REPRESENTABLE
        else -> LineHeightMetadata.NONE
    }

    fun propertyInitializer(call: IrCall): IrExpression? {
        val property = call.symbol.owner.correspondingPropertySymbol?.owner ?: return null
        if (sourceFile(property) == null) return null
        return property.backingField?.initializer?.expression ?: when (val body = property.getter?.body) {
            is IrExpressionBody -> body.expression
            is IrBlockBody -> body.statements.filterIsInstance<IrReturn>().lastOrNull()?.value
            else -> null
        }
    }

    fun unwrap(value: IrExpression): IrExpression? = when (value) {
        is IrGetValue -> scope.aliases[value.symbol]
            ?: (value.symbol.owner as? IrVariable)?.takeUnless { it.isVar }?.initializer
        is IrGetField -> value.symbol.owner.initializer?.expression
        is IrTypeOperatorCall -> value.argument
        is IrBlock -> value.statements.lastOrNull() as? IrExpression
        is IrCall -> propertyInitializer(value)
        else -> null
    }

    fun constant(value: IrExpression?, kind: String): String? {
        if (value == null || !constantVisited.add(value)) return null
        unwrap(value)?.let { return constant(it, kind) }
        val call = value as? IrCall ?: return null
        val property = call.symbol.owner.correspondingPropertySymbol?.owner ?: return null
        val parent = property.parent as? IrClass ?: return null
        return property.name.asString().takeIf {
            symbolName(parent) == "androidx.compose.ui.text.style.LineHeightStyle.$kind.Companion"
        }
    }

    fun semantic(value: IrExpression?): LineHeightSemantic? {
        if (value == null || !semanticVisited.add(value)) return null
        unwrap(value)?.let { return semantic(it) }
        if (value is IrConstructorCall) {
            val owner = value.symbol.owner.parent as? IrClass ?: return null
            if (symbolName(owner) != "androidx.compose.ui.text.style.LineHeightStyle") return null
            return LineHeightSemantic(constant(argument(value, "alignment"), "Alignment") ?: return null,
                constant(argument(value, "trim"), "Trim") ?: return null,
                constant(argument(value, "mode"), "Mode") ?: "Fixed")
        }
        val call = value as? IrCall ?: return null
        val api = symbolName(call.symbol.owner)
        val property = call.symbol.owner.correspondingPropertySymbol?.owner
        if (property != null && symbolName(property.parent as? IrClass ?: return null) ==
            "androidx.compose.ui.text.style.LineHeightStyle.Companion" && property.name.asString() == "Default")
            return LineHeightSemantic("Proportional", "Both", "Fixed")
        if (api == "androidx.compose.ui.text.style.LineHeightStyle.copy") {
            val base = semantic(call.dispatchReceiver) ?: return null
            return LineHeightSemantic(constant(argument(call, "alignment"), "Alignment") ?: base.alignment,
                constant(argument(call, "trim"), "Trim") ?: base.trim,
                constant(argument(call, "mode"), "Mode") ?: base.mode)
        }
        return null
    }

    lateinit var metadata: (IrExpression) -> LineHeightMetadata
    fun relevantReturns(function: IrSimpleFunction): List<IrExpression> = when (val body = function.body) {
        is IrExpressionBody -> listOf(body.expression)
        is IrBlockBody -> body.statements.filterIsInstance<IrReturn>()
            .filter { it.returnTargetSymbol == function.symbol }.map { it.value }
        else -> emptyList()
    }
    metadata = fun(value: IrExpression): LineHeightMetadata {
        if (!traversed.add(value)) return LineHeightMetadata.UNSUPPORTED
        unwrap(value)?.let { return metadata(it) }
        val type = value.type.classOrNull?.owner?.let(::symbolName)
        if (type == "androidx.compose.ui.text.style.LineHeightStyle") {
            val resolved = semantic(value) ?: return LineHeightMetadata.UNSUPPORTED
            return if (resolved == LineHeightSemantic("Center", "None", "Fixed"))
                LineHeightMetadata.REPRESENTABLE else LineHeightMetadata.UNSUPPORTED
        }
        val call = value as? IrCall
        val api = call?.symbol?.owner?.let(::symbolName)
        if (type == "androidx.compose.ui.text.TextStyle") {
            if (value is IrConstructorCall && symbolName(value.symbol.owner.parent as IrClass) ==
                "androidx.compose.ui.text.TextStyle") {
                return argument(value, "lineHeightStyle")?.let(metadata) ?: LineHeightMetadata.NONE
            }
            if (api == "androidx.compose.ui.text.TextStyle.copy")
                return argument(call, "lineHeightStyle")?.let(metadata)
                    ?: call.dispatchReceiver?.let(metadata) ?: LineHeightMetadata.UNSUPPORTED
            val property = call?.symbol?.owner?.correspondingPropertySymbol?.owner
            if (property != null && symbolName(property.parent as? IrClass ?: return LineHeightMetadata.UNSUPPORTED) ==
                "androidx.compose.material3.Typography") {
                return if (LINE_HEIGHT_STYLE_CONTEXT in scope.semanticFlags) LineHeightMetadata.UNSUPPORTED
                    else LineHeightMetadata.NONE
            }
            val source = call?.symbol?.owner?.takeIf { sourceFile(it) != null }
            if (source != null) return combine(relevantReturns(source).map(metadata))
            return LineHeightMetadata.UNSUPPORTED
        }
        if (type == "androidx.compose.material3.Typography") {
            if (value is IrConstructorCall && symbolName(value.symbol.owner.parent as IrClass) ==
                "androidx.compose.material3.Typography") {
                return combine(value.symbol.owner.valueParameters.indices.mapNotNull { index ->
                    value.getValueArgument(index)?.let(metadata)
                })
            }
            val source = call?.symbol?.owner?.takeIf { sourceFile(it) != null }
            if (source != null) return combine(relevantReturns(source).map(metadata))
            return LineHeightMetadata.UNSUPPORTED
        }
        return LineHeightMetadata.NONE
    }
    return metadata(expression) == LineHeightMetadata.UNSUPPORTED
}
