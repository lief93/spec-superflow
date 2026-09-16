@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.*

internal class ComposePaddingValuesRule : CallRule {
    override fun mapType(type: IrType, language: Language): EtsType? =
        type.classOrNull?.owner?.takeIf { sourceFile(it) == null &&
            symbolName(it) == "androidx.compose.foundation.layout.PaddingValues" }?.let { paddingType }

    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        val owner = call.symbol.owner
        if (sourceFile(owner) != null || symbolName(owner) != "androidx.compose.foundation.layout.PaddingValues") return null
        val at = language.source(call)
        val names = owner.valueParameters.map { it.name.asString() }
        fun value(name: String) = argument(call, name)?.let { language.expression(it, scope) } ?: EtsLiteral(0, EtsTypes.NUMBER, at)
        return when (names) {
            listOf("all") -> uniformPadding(value("all"), at)
            listOf("horizontal", "vertical") -> symmetricPadding(value("horizontal"), value("vertical"), at)
            listOf("start", "top", "end", "bottom") -> edgePadding(names.map(::value), at)
            else -> throw Unsupported(Diagnostic("UNSUPPORTED", "Unsupported PaddingValues factory signature", at))
        }
    }
}
