package dev.ets

import org.jetbrains.kotlin.ir.expressions.*

/** Follow Kotlin/JS VarargLowering's segment ordering and single-spread copy. */
internal fun lowerVararg(value: IrVararg, language: Language, scope: Scope): EtsExpression {
    val at = language.source(value)
    val element = language.type(value.varargElementType)
    val array = EtsNamedType("Array", listOf(element))
    val segments = mutableListOf<EtsExpression>()
    val items = mutableListOf<EtsExpression>()
    fun flush() {
        if (items.isNotEmpty()) {
            segments += EtsArray(items.toList(), element, at)
            items.clear()
        }
    }
    value.elements.forEach { item -> when (item) {
        is IrSpreadElement -> {
            flush()
            segments += language.expression(item.expression, scope)
        }
        is IrExpression -> items += language.expression(item, scope)
    } }
    flush()
    if (segments.isEmpty()) return EtsArray(emptyList(), element, at)
    if (segments.size == 1) {
        val result = segments.single()
        return if (value.elements.any { it is IrSpreadElement })
            EtsCall(EtsMember(result, "slice", EtsFunctionType(emptyList(), array), at), emptyList(), array, at)
        else result
    }
    // All segments are evaluated before concat, as in the official JS intrinsic.
    return EtsCall(EtsMember(EtsArray(emptyList(), element, at), "concat",
        EtsFunctionType(List(segments.size) { array }, array), at), segments, array, at)
}
