@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.expressions.IrCall

/** Generated applications run in a native host, not inside Compose's inspection tool. */
internal class ComposeInspectionModeRule : CallRule {
    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        if (!isCompositionLocalCurrent(call.symbol.owner)) return null
        if (compositionLocalName(call.dispatchReceiver, scope) != "androidx.compose.ui.platform.LocalInspectionMode") return null
        return EtsLiteral(false, EtsTypes.BOOLEAN, language.source(call))
    }
}
