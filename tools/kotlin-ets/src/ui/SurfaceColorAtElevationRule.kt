@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import dev.ets.widgets.SurfaceColorAtElevation
import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.expressions.IrExpression
import org.jetbrains.kotlin.ir.types.classOrNull

private const val surfaceColorAtElevationApi = "androidx.compose.material3.surfaceColorAtElevation"
private const val composeDpClass = "androidx.compose.ui.unit.Dp"

/** Applies Material's tonal elevation formula to a typed ColorScheme and runtime Dp value. */
internal class ComposeSurfaceColorAtElevationRule : CallRule {
    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        val owner = call.symbol.owner
        if (sourceFile(owner) != null || symbolName(owner) != surfaceColorAtElevationApi) return null
        val at = language.source(call)
        val receiver = call.extensionReceiver
        val elevation = call.getValueArgument(0)
        if (owner.typeParameters.isNotEmpty() || owner.dispatchReceiverParameter != null ||
            owner.extensionReceiverParameter?.type?.classOrNull?.owner?.let(::symbolName) !=
                "androidx.compose.material3.ColorScheme" ||
            owner.valueParameters.size != 1 || owner.valueParameters.single().name.asString() != "elevation" ||
            owner.valueParameters.single().type.classOrNull?.owner?.let(::symbolName) != composeDpClass ||
            owner.returnType.classOrNull?.owner?.let(::symbolName) != colorType ||
            call.type.classOrNull?.owner?.let(::symbolName) != colorType || receiver == null || elevation == null)
            throw Unsupported(Diagnostic("UNSUPPORTED", "Unsupported Material3 surfaceColorAtElevation signature", at))
        return lower(SurfaceColorAtElevation(receiver, elevation, at), language, scope)
    }

    private fun lower(value: SurfaceColorAtElevation<IrExpression, SourceSpan>, language: Language,
        scope: Scope): EtsExpression = EtsCall(EtsReference(surfaceColorAtElevation, value.source), listOf(
            language.expression(value.colorScheme, scope), requireSpecifiedDp(language.expression(value.elevation, scope),
                language.source(value.elevation), "surfaceColorAtElevation")),
        EtsTypes.NUMBER, value.source)
}
