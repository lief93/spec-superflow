@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.dependency.klib

import dev.ets.*
import org.jetbrains.kotlin.ir.declarations.IrClass
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.symbols.IrConstructorSymbol
import org.jetbrains.kotlin.ir.symbols.IrFunctionSymbol
import org.jetbrains.kotlin.ir.types.IrSimpleType
import org.jetbrains.kotlin.ir.types.IrType
import org.jetbrains.kotlin.ir.types.IrTypeProjection
import org.jetbrains.kotlin.ir.types.classOrNull
import org.jetbrains.kotlin.ir.types.isNullable
import org.jetbrains.kotlin.ir.util.parentAsClass
import org.jetbrains.kotlin.types.Variance

/** Canonical KLIB symbols for the residual collection boundary of an approved common body. */
data class KlibCollectionRuntimeBindings(
    val emptyListConstructor: IrConstructorSymbol,
    val iterator: IrFunctionSymbol,
    val hasNext: IrFunctionSymbol,
    val next: IrFunctionSymbol,
    val append: IrFunctionSymbol,
) {
    init {
        require(listOf(emptyListConstructor, iterator, hasNext, next, append).all { it.isBound }) {
            "Collection runtime bindings require canonical linked KLIB symbols"
        }
        require(emptyListConstructor.owner.parent is IrClass) {
            "The empty-list constructor must belong to a linked KLIB class"
        }
    }
}

/**
 * Typed target representation for the collection operations left after common-body inlining.
 * Source API selection is by symbol identity only; helper names identify target runtime primitives.
 */
class KlibCollectionRuntimeRule(private val bindings: KlibCollectionRuntimeBindings) : CallRule {
    private val listClass = bindings.emptyListConstructor.owner.parentAsClass.symbol
    private val mutableCollectionClass = bindings.append.owner.parentAsClass.symbol

    override fun mapType(type: IrType, language: Language): EtsType? {
        val element = type.collectionElement(setOf(listClass.owner, mutableCollectionClass.owner)) ?: return null
        return EtsNamedType("Array", listOf(language.type(element)))
    }

    override fun lowerConstructor(call: IrConstructorCall, language: Language, scope: Scope): EtsExpression? {
        if (call.symbol !== bindings.emptyListConstructor) return null
        if (call.valueArgumentsCount != 0 || call.dispatchReceiver != null || call.extensionReceiver != null) return null
        val element = call.type.collectionElement(setOf(listClass.owner), invariant = true) ?: return null
        if (call.typeArgumentsCount != listClass.owner.typeParameters.size ||
            (0 until call.typeArgumentsCount).any { call.getTypeArgument(it) == null } ||
            call.getTypeArgument(0) != element) return null
        val targetElement = language.type(element)
        if (language.type(call.type) != EtsNamedType("Array", listOf(targetElement))) return null
        return EtsArray(emptyList(), targetElement, language.source(call))
    }

    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        val operation = when {
            call.symbol === bindings.iterator -> Operation.ITERATOR
            call.symbol === bindings.hasNext -> Operation.HAS_NEXT
            call.symbol === bindings.next -> Operation.NEXT
            call.symbol === bindings.append -> Operation.APPEND
            else -> return null
        }
        if (call.superQualifierSymbol != null || call.typeArgumentsCount != 0) return null
        val receiverExpression = call.dispatchReceiver ?: call.extensionReceiver ?: return null
        if (call.dispatchReceiver != null && call.extensionReceiver != null) return null
        val at = language.source(call)
        val receiverType = language.type(receiverExpression.type)
        val result = language.type(call.type)

        fun member(receiver: EtsExpression, name: String): EtsExpression = EtsCall(
            EtsMember(receiver, name, EtsFunctionType(emptyList(), result), at), emptyList(), result, at)

        return when (operation) {
            Operation.ITERATOR -> {
                if (call.valueArgumentsCount != 0) return null
                val array = receiverType.arrayElement() ?: return null
                if (result != EtsNamedType("__etsIterator", listOf(array), "stdlib:__etsIterator", external = true)) return null
                val receiver = language.expression(receiverExpression, scope)
                val failFast = EtsLiteral(true, EtsTypes.BOOLEAN, at)
                external("__etsArrayIterator", listOf(receiver, failFast), result, at, listOf(array))
            }
            Operation.HAS_NEXT -> {
                if (call.valueArgumentsCount != 0 || receiverType.iteratorElement() == null || result != EtsTypes.BOOLEAN) return null
                member(language.expression(receiverExpression, scope), "hasNext")
            }
            Operation.NEXT -> {
                if (call.valueArgumentsCount != 0 || receiverType.iteratorElement() != result) return null
                member(language.expression(receiverExpression, scope), "next")
            }
            Operation.APPEND -> {
                if (call.valueArgumentsCount != 1 || result != EtsTypes.BOOLEAN) return null
                val element = receiverType.arrayElement() ?: return null
                val valueExpression = call.getValueArgument(0) ?: return null
                if (language.type(valueExpression.type) != element) return null
                val receiver = language.expression(receiverExpression, scope)
                val value = language.expression(valueExpression, scope)
                external("__etsListAdd", listOf(receiver, value), result, at, listOf(element))
            }
        }
    }

    private fun external(name: String, arguments: List<EtsExpression>, result: EtsType, at: SourceSpan,
        types: List<EtsType>): EtsExpression = EtsCall(
        EtsReference(EtsSymbol("stdlib:$name", name, EtsFunctionType(arguments.map { it.type }, result), at,
            external = true)), arguments, result, at, types)

    private enum class Operation { ITERATOR, HAS_NEXT, NEXT, APPEND }
}

private fun IrType.collectionElement(expected: Set<IrClass>, invariant: Boolean = false): IrType? {
    val simple = this as? IrSimpleType ?: return null
    if (simple.isNullable() || simple.classOrNull?.owner !in expected || simple.arguments.size != 1) return null
    val projection = simple.arguments.single() as? IrTypeProjection ?: return null
    return projection.type.takeIf { !invariant || projection.variance == Variance.INVARIANT }
}

private fun EtsType.arrayElement(): EtsType? =
    (this as? EtsNamedType)?.takeIf { it.name == "Array" && it.arguments.size == 1 }?.arguments?.single()

private fun EtsType.iteratorElement(): EtsType? =
    (this as? EtsNamedType)?.takeIf {
        it.name == "__etsIterator" && it.symbolId == "stdlib:__etsIterator" && it.external && it.arguments.size == 1
    }?.arguments?.single()
