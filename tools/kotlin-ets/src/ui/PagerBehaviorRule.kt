@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.expressions.IrGetObjectValue
import org.jetbrains.kotlin.ir.types.IrType
import org.jetbrains.kotlin.ir.types.classOrNull

private val pagerSnapPositionType = EtsNamedType("__etsPagerSnapPosition", external = true)
private val pagerFlingBehaviorType = EtsNamedType("__etsPagerFlingBehavior", external = true)

/** Typed marker values keep Compose compiler temporaries intact until HorizontalPager consumes them. */
internal class ComposePagerBehaviorRule : CallRule {
    override fun mapType(type: IrType, language: Language): EtsType? = when (
        type.classOrNull?.owner?.let(::symbolName)
    ) {
        "androidx.compose.foundation.gestures.snapping.SnapPosition" -> pagerSnapPositionType
        "androidx.compose.foundation.gestures.FlingBehavior",
        "androidx.compose.foundation.gestures.TargetedFlingBehavior" -> pagerFlingBehaviorType
        else -> null
    }

    override fun isStableValue(call: IrCall): Boolean =
        symbolName(call.symbol.owner) == "androidx.compose.foundation.pager.PagerDefaults.flingBehavior"

    override fun isStableObject(value: IrGetObjectValue): Boolean =
        symbolName(value.symbol.owner) ==
            "androidx.compose.foundation.gestures.snapping.SnapPosition.Center"

    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        if (!isStableValue(call)) return null
        return EtsReference(EtsSymbol("compose:pager:default-fling", "__etsPagerDefaultFlingBehavior",
            pagerFlingBehaviorType, language.source(call), external = true))
    }

    override fun lowerObject(value: IrGetObjectValue, language: Language, scope: Scope): EtsExpression? {
        if (!isStableObject(value)) return null
        return EtsReference(EtsSymbol("compose:pager:snap-center", "__etsPagerSnapCenter",
            pagerSnapPositionType, language.source(value), external = true))
    }
}
