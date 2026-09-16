@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.types.IrType
import org.jetbrains.kotlin.ir.types.classOrNull

/** Read the native host during composition; do not fabricate an Android Context. */
internal class ComposeLocalContextRule : CallRule {
    private val contextType = EtsNamedType("Context", external = true)

    override fun mapType(type: IrType, language: Language): EtsType? = type.classOrNull?.owner?.let {
        if (sourceFile(it) == null && symbolName(it) == "android.content.Context") contextType else null
    }

    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        val owner = call.symbol.owner
        if (sourceFile(owner) != null) return null
        val property = owner.correspondingPropertySymbol?.owner?.let(::symbolName)
        if (property !in setOf("androidx.compose.runtime.CompositionLocal.current",
                "androidx.compose.runtime.ProvidableCompositionLocal.current")) return null
        val receiver = call.dispatchReceiver as? IrCall ?: return null
        if (sourceFile(receiver.symbol.owner) != null ||
            receiver.symbol.owner.correspondingPropertySymbol?.owner?.let(::symbolName) != "androidx.compose.ui.platform.LocalContext") return null
        val at = language.source(call)
        val native = EtsSymbol("arkui:getContext", "getContext", EtsFunctionType(emptyList(), contextType), at, external = true)
        return EtsCall(EtsReference(native), emptyList(), contextType, at)
    }
}
