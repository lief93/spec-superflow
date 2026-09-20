@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.expressions.IrGetField
import org.jetbrains.kotlin.ir.types.IrType
import org.jetbrains.kotlin.ir.types.classOrNull

internal val nativeHostContextType = EtsNamedType("Context", external = true)
internal val compositionLocalType = EtsNamedType("EtsCompositionLocal", symbolId = "compose:compositionLocal", external = true)
private val localContextMarker = EtsSymbol("compose:localContext", "__etsLocalContext", compositionLocalType,
    SourceSpan("EtsLocalContext.kt", 0, 0), external = true)

/** Read the native host during composition; do not fabricate an Android Context. */
internal class ComposeLocalContextRule : CallRule {
    override fun mapType(type: IrType, language: Language): EtsType? = type.classOrNull?.owner?.let {
        when (symbolName(it)) {
            "android.content.Context" -> if (sourceFile(it) == null) nativeHostContextType else null
            "androidx.compose.runtime.CompositionLocal",
            "androidx.compose.runtime.ProvidableCompositionLocal" -> compositionLocalType
            else -> null
        }
    }

    override fun lowerField(value: IrGetField, language: Language, scope: Scope): EtsExpression? {
        val name = value.symbol.owner.correspondingPropertySymbol?.owner?.let(::symbolName)
            ?: symbolName(value.symbol.owner)
        return if (name == "androidx.compose.ui.platform.LocalContext")
            EtsReference(localContextMarker, language.source(value)) else null
    }

    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        val owner = call.symbol.owner
        val at = language.source(call)
        val local = compositionLocalName(call, scope)
            ?: compositionLocalName(call.dispatchReceiver, scope)
        if (local == "androidx.compose.ui.platform.LocalContext" && !isCompositionLocalCurrent(owner))
            return EtsReference(localContextMarker, at)
        if (!isCompositionLocalCurrent(owner)) return null
        if (compositionLocalName(call.dispatchReceiver, scope) != "androidx.compose.ui.platform.LocalContext") return null
        val native = EtsSymbol("arkui:getContext", "getContext", EtsFunctionType(emptyList(), nativeHostContextType), at, external = true)
        return EtsCall(EtsReference(native), emptyList(), nativeHostContextType, at)
    }
}
