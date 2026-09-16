@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.declarations.IrVariable
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.symbols.IrValueSymbol
import org.jetbrains.kotlin.ir.visitors.*

internal fun projectionLocalReads(body: IrBlockBody): Map<IrValueSymbol, Int> {
    val counts = mutableMapOf<IrValueSymbol, Int>()
    body.acceptVoid(object : IrElementVisitorVoid {
        override fun visitElement(element: IrElement) {
            if (element is IrGetValue) counts.merge(element.symbol, 1, Int::plus)
            element.acceptChildrenVoid(this)
        }
    })
    return counts
}

/** Only remove immutable locals made unused by an explicit, diagnosed UI projection. */
internal fun pruneProjectedLocals(body: IrBlockBody, originalReads: Map<IrValueSymbol, Int>, diagnostics: DiagnosticSink) {
    do {
        var changed = false
        val liveReads = projectionLocalReads(body)
        body.acceptVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) {
                val statements = when (element) {
                    is IrBlockBody -> element.statements
                    is IrContainerExpression -> element.statements
                    else -> null
                }
                statements?.removeAll { statement ->
                    val discard = statement is IrVariable && !statement.isVar &&
                        originalReads.getOrDefault(statement.symbol, 0) > 0 && liveReads.getOrDefault(statement.symbol, 0) == 0
                    if (discard) { diagnostics.omittedUiElements.add(statement); changed = true }
                    discard
                }
                element.acceptChildrenVoid(this)
            }
        })
    } while (changed)
}
