@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.declarations.IrValueParameter
import org.jetbrains.kotlin.ir.expressions.*

internal data class TouchTargets(
    val box: IrCall, val index: IrValueParameter, val count: Int,
    val inset: Double, val width: Double, val height: Double,
    val rowHorizontal: Double, val rowVertical: Double,
    val padding: Map<IrCall, Double>,
) {
    val expandX get() = maxOf(0.0, (48.0 - width) / 2)
    val expandY get() = maxOf(0.0, (48.0 - height) / 2)
    private fun region(values: Map<String, Any>, source: SourceSpan): EtsObject {
        val fields = values.mapValues { (_, value) -> EtsLiteral(value, if (value is String) EtsTypes.STRING else EtsTypes.NUMBER, source) }
        return EtsObject(fields, EtsRecordType("Rectangle", fields.mapValues { it.value.type }), source)
    }
    fun region(origin: Double, source: SourceSpan): EtsObject = region(linkedMapOf(
        "x" to inset - origin - expandX, "y" to inset - origin - expandY, "width" to maxOf(48.0, width), "height" to maxOf(48.0, height)), source)
    fun rowRegion(source: SourceSpan): EtsObject {
        val x = maxOf(0.0, expandX - inset - rowHorizontal)
        val y = maxOf(0.0, expandY - inset - rowVertical)
        return region(linkedMapOf("x" to -x, "y" to -y, "width" to "calc(100% + ${2 * x}vp)", "height" to "calc(100% + ${2 * y}vp)"), source)
    }
}

/** Bounded homogeneous sibling group; native hit testing supplies actual child positions. */
internal fun touchTargets(row: IrCall, scope: Scope, diagnostics: DiagnosticSink): TouchTargets? {
    fun resolve(value: IrExpression?): IrExpression? =
        if (value is IrGetValue && value.symbol in scope.aliases) resolve(scope.aliases[value.symbol]) else value
    fun onlyCall(body: IrBody?): IrCall? {
        val statement = (body as? IrBlockBody)?.statements?.singleOrNull() ?: return null
        return ((statement as? IrReturn)?.value ?: statement) as? IrCall
    }
    val content = lambda(argument(row, "content"), scope) ?: return null
    val repeat = onlyCall(content.body) ?: return null
    if (symbolName(repeat.symbol.owner) != "kotlin.repeat") return null
    val action = lambda(argument(repeat, "action"), scope) ?: return null
    val box = onlyCall(action.body) ?: return null
    if (symbolName(box.symbol.owner) != "androidx.compose.foundation.layout.Box") return null
    fun operations(value: IrExpression?): List<IrCall> = when (val resolved = resolve(value)) {
        is IrCall -> operations(resolved.extensionReceiver ?: resolved.dispatchReceiver) + resolved
        is IrGetObjectValue, null -> emptyList()
        else -> diagnostics.unsupported(resolved, "Touch target requires a resolved Modifier chain")
    }
    val operations = operations(argument(box, "modifier"))
    val click = operations.indexOfFirst { symbolName(it.symbol.owner) == "androidx.compose.foundation.clickable" }
    if (click < 0) return null
    val count = (resolve(argument(repeat, "times")) as? IrConst)?.value as? Int
        ?: diagnostics.unsupported(repeat, "Touch group requires a constant repeat count")
    if (count < 1) diagnostics.unsupported(repeat, "Touch group requires a positive repeat count")
    if (argument(box, "content") != null) diagnostics.unsupported(box, "Touch target group currently requires empty source Boxes")
    fun dp(value: IrExpression?): Double {
        val call = resolve(value) as? IrCall ?: diagnostics.unsupported(box, "Touch target geometry requires constant dp")
        val property = call.symbol.owner.correspondingPropertySymbol?.owner?.let(::symbolName)
        if (property != "androidx.compose.ui.unit.dp") diagnostics.unsupported(call, "Touch target geometry requires dp")
        val number = (resolve(call.extensionReceiver) as? IrConst)?.value as? Number
            ?: diagnostics.unsupported(call, "Touch target geometry currently requires constant dp")
        val result = number.toDouble()
        if (!result.isFinite() || result < 0) diagnostics.unsupported(call, "Invalid touch target dimension")
        return result
    }
    var width: Double? = null
    var height: Double? = null
    val padding = linkedMapOf<IrCall, Double>()
    var afterClick = 0.0
    var inset = 0.0
    operations.forEachIndexed { index, call ->
        when (symbolName(call.symbol.owner)) {
            "androidx.compose.foundation.layout.width" -> {
                if (width != null) diagnostics.unsupported(call, "Repeated touch target width is unsupported")
                width = dp(argument(call, "width"))
            }
            "androidx.compose.foundation.layout.height" -> {
                if (height != null) diagnostics.unsupported(call, "Repeated touch target height is unsupported")
                height = dp(argument(call, "height"))
            }
            "androidx.compose.foundation.layout.padding" -> {
                if (width != null || height != null) diagnostics.unsupported(call, "Touch group requires padding outside fixed dimensions")
                val amount = dp(argument(call, "all"))
                padding[call] = amount
                if (index < click) inset += amount else afterClick += amount
            }
            "androidx.compose.foundation.clickable" -> {
                if (index != click) diagnostics.unsupported(call, "Multiple clickable layers in a touch group are unsupported")
                val enabled = argument(call, "enabled")
                if (enabled != null && (resolve(enabled) as? IrConst)?.value != true)
                    diagnostics.unsupported(enabled, "Touch group arbitration currently requires enabled targets")
            }
            "androidx.compose.foundation.background", "androidx.compose.ui.platform.testTag" -> Unit
            else -> diagnostics.unsupported(call, "Unsupported touch group modifier")
        }
    }
    var horizontal = 0.0
    var vertical = 0.0
    for (call in operations(argument(row, "modifier"))) {
        when (symbolName(call.symbol.owner)) {
            "androidx.compose.foundation.layout.padding" -> {
                if (argument(call, "all") != null) {
                    val amount = dp(argument(call, "all")); horizontal += amount; vertical += amount
                } else {
                    if (call.symbol.owner.valueParameters.none { it.name.asString() == "horizontal" })
                        diagnostics.unsupported(call, "Touch group requires symmetric Row padding")
                    horizontal += argument(call, "horizontal")?.let(::dp) ?: 0.0
                    vertical += argument(call, "vertical")?.let(::dp) ?: 0.0
                }
            }
            "androidx.compose.foundation.background", "androidx.compose.ui.platform.testTag" -> Unit
            else -> diagnostics.unsupported(call, "Touch group requires unconstrained Row geometry")
        }
    }
    return TouchTargets(box, action.valueParameters.single(), count, inset,
        (width ?: diagnostics.unsupported(box, "Touch target requires explicit width")) + 2 * afterClick,
        (height ?: diagnostics.unsupported(box, "Touch target requires explicit height")) + 2 * afterClick,
        horizontal, vertical, padding)
}

internal val touchTargetSupport = """
function __etsNearestTouch(items: TouchTestInfo[], inset: number, width: number, height: number): TouchResult {
  let selected: string = '';
  let best: number = Number.POSITIVE_INFINITY;
  for (let index = 0; index < items.length; index++) {
    const item = items[index];
    const x = item.x - inset;
    const y = item.y - inset;
    const dx = Math.max(0, -x, x - width);
    const dy = Math.max(0, -y, y - height);
    if (dx <= Math.max(0, (48 - width) / 2) && dy <= Math.max(0, (48 - height) / 2)) {
      const distance = dx * dx + dy * dy;
      if (distance < best) { selected = item.id; best = distance; }
    }
  }
  return selected.length > 0 ? { strategy: TouchTestStrategy.FORWARD, id: selected }
    : { strategy: TouchTestStrategy.DEFAULT };
}
""".trimIndent().lines()
