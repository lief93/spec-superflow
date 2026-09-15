@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.expressions.IrCall

/** Generated applications run in a native host, not inside Compose's inspection tool. */
internal class ComposeInspectionModeRule : CallRule {
    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        val property = call.symbol.owner.correspondingPropertySymbol?.owner?.let(::symbolName)
        if (property !in setOf("androidx.compose.runtime.CompositionLocal.current", "androidx.compose.runtime.ProvidableCompositionLocal.current")) return null
        val receiver = call.dispatchReceiver as? IrCall ?: return null
        if (receiver.symbol.owner.correspondingPropertySymbol?.owner?.let(::symbolName) != "androidx.compose.ui.platform.LocalInspectionMode") return null
        return EtsLiteral(false, EtsTypes.BOOLEAN, language.source(call))
    }
}
