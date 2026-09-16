@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.types.isLong

internal object LongValueRule : CallRule {
    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        if (symbolName(call.symbol.owner) != "kotlin.Long.unaryMinus" || call.valueArgumentsCount != 0) return null
        val receiver = call.dispatchReceiver ?: return null
        if (!receiver.type.isLong() || !call.type.isLong()) return null
        val at = language.source(call)
        val native = EtsReference(EtsSymbol("native:BigInt", "BigInt", EtsTypes.OBJECT, at, external = true))
        return EtsCall(EtsMember(native, "asIntN",
            EtsFunctionType(listOf(EtsTypes.NUMBER, EtsTypes.BIGINT), EtsTypes.BIGINT), at),
            listOf(EtsLiteral(64, EtsTypes.NUMBER, at),
                EtsUnary("-", language.expression(receiver, scope), EtsTypes.BIGINT, at)), EtsTypes.BIGINT, at)
    }
}
