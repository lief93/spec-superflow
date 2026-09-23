@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.IrType
import org.jetbrains.kotlin.ir.types.classOrNull

private val gradientStopType = EtsTupleType(listOf(EtsTypes.NUMBER, EtsTypes.NUMBER))
private val gradientStopsType = EtsNamedType("Array", listOf(gradientStopType))
internal val linearGradientType = EtsRecordType("LinearGradient", linkedMapOf(
    "angle" to EtsTypes.NUMBER,
    "colors" to gradientStopsType,
))

/** Maps resolved Compose linear brushes to ArkUI's native LinearGradient value. */
internal class ComposeBrushRule(private val diagnostics: DiagnosticSink) : CallRule {
    override fun mapType(type: IrType, language: Language): EtsType? {
        val owner = type.classOrNull?.owner ?: return null
        return linearGradientType.takeIf {
            sourceFile(owner) == null && symbolName(owner) == "androidx.compose.ui.graphics.Brush"
        }
    }

    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        val name = symbolName(call.symbol.owner)
        if (sourceFile(call.symbol.owner) != null || name !in setOf(
                "androidx.compose.ui.graphics.Brush.Companion.linearGradient",
                "androidx.compose.ui.graphics.Brush.Companion.horizontalGradient",
                "androidx.compose.ui.graphics.Brush.Companion.verticalGradient",
            )) return null
        val colors = argument(call, "colors") ?: diagnostics.unsupported(call, "Linear gradient requires colors")
        val values = listElements(colors, scope)
        if (values.size < 2) diagnostics.unsupported(colors, "Linear gradient requires at least two colors")
        val stops = values.mapIndexed { index, value ->
            val color = requireSpecifiedColor(language.expression(value, scope), language.source(value),
                "Brush.linearGradient color")
            val position = EtsLiteral(index.toDouble() / (values.size - 1), EtsTypes.NUMBER, language.source(value))
            EtsCast(EtsArray(listOf(color, position), EtsTypes.NUMBER, language.source(value)),
                gradientStopType, language.source(value))
        }
        val angle = when {
            name.endsWith(".horizontalGradient") -> 90.0
            name.endsWith(".verticalGradient") -> 180.0
            else -> gradientAngle(argument(call, "start"), argument(call, "end"), scope)
        }
        return EtsObject(linkedMapOf(
            "angle" to EtsLiteral(angle, EtsTypes.NUMBER, language.source(call)),
            "colors" to EtsArray(stops, gradientStopType, language.source(colors)),
        ), linearGradientType, language.source(call))
    }

    private fun resolve(value: IrExpression, scope: Scope): IrExpression = when (value) {
        is IrGetValue -> scope.aliases[value.symbol]?.let { resolve(it, scope) } ?: value
        is IrBlock -> (value.statements.lastOrNull() as? IrExpression)?.let { resolve(it, scope) } ?: value
        else -> value
    }

    private fun listElements(value: IrExpression, scope: Scope): List<IrExpression> {
        val call = resolve(value, scope) as? IrCall
            ?: diagnostics.unsupported(value, "Linear gradient colors require a resolved listOf value")
        if (symbolName(call.symbol.owner) != "kotlin.collections.listOf")
            diagnostics.unsupported(value, "Linear gradient colors require listOf")
        val elements = call.getValueArgument(0) as? IrVararg
            ?: diagnostics.unsupported(value, "Linear gradient colors require explicit elements")
        return elements.elements.map {
            it as? IrExpression ?: diagnostics.unsupported(it, "Linear gradient color spreads are unsupported")
        }
    }

    private fun gradientAngle(start: IrExpression?, end: IrExpression?, scope: Scope): Double {
        if (start == null && end == null) return 135.0
        fun offset(value: IrExpression?): Pair<Double, Double>? {
            val call = value?.let { resolve(it, scope) } as? IrConstructorCall ?: return null
            if ((call.symbol.owner.parent as? org.jetbrains.kotlin.ir.declarations.IrClass)
                    ?.let(::symbolName) != "androidx.compose.ui.geometry.Offset") return null
            fun number(name: String): Double? {
                val expression = argument(call, name)?.let { resolve(it, scope) } ?: return null
                val constant = (expression as? IrConst)?.value as? Number
                if (constant != null) return constant.toDouble()
                val getter = expression as? IrCall ?: return null
                return if (getter.symbol.owner.correspondingPropertySymbol?.owner?.let(::symbolName) ==
                    "kotlin.Float.Companion.POSITIVE_INFINITY") Double.POSITIVE_INFINITY else null
            }
            return Pair(number("x") ?: return null, number("y") ?: return null)
        }
        val from = offset(start) ?: return 135.0
        val to = offset(end) ?: return 135.0
        return if (from.first == 0.0 && from.second.isInfinite() && to.first.isInfinite() && to.second == 0.0) 45.0
            else 135.0
    }
}
