@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.compose

import dev.ets.*
import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.types.isUnit
import org.jetbrains.kotlin.ir.util.hasAnnotation
import org.jetbrains.kotlin.name.FqName

/** Source UI functions must be consumed as widgets, never as ordinary value/effect calls. */
class ComposeSourceUiCallGuardRule(private val diagnostics: DiagnosticSink) : CallRule {
    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        val function = call.symbol.owner
        if (sourceFile(function) != null && !function.isExternal && function.returnType.isUnit() &&
            function.hasAnnotation(composable)) {
            diagnostics.unsupported(call,
                "Source UI builder cannot execute inside a value helper or ordinary expression")
        }
        return null
    }

    private companion object {
        val composable = FqName("androidx.compose.runtime.Composable")
    }
}
