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
    val emptyListConstructor: IrConstructorSymbol? = null,
    val iterator: IrFunctionSymbol,
    val hasNext: IrFunctionSymbol,
    val next: IrFunctionSymbol,
    val isEmpty: IrFunctionSymbol? = null,
    val get: IrFunctionSymbol? = null,
    val append: IrFunctionSymbol? = null,
    val appendAll: IrFunctionSymbol? = null,
    val capacityListConstructor: IrConstructorSymbol? = null,
    val collectionSizeOrDefault: IrFunctionSymbol? = null,
    val checkIndexOverflow: IrFunctionSymbol? = null,
) {
    init {
        require(listOfNotNull(emptyListConstructor, iterator, hasNext, next, isEmpty, get, append, appendAll,
            capacityListConstructor, collectionSizeOrDefault, checkIndexOverflow).all { it.isBound }) {
            "Collection runtime bindings require canonical linked KLIB symbols"
        }
        require(emptyListConstructor == null || emptyListConstructor.owner.parent is IrClass) {
            "The empty-list constructor must belong to a linked KLIB class"
        }
        require(capacityListConstructor == null ||
            capacityListConstructor.owner.parent === emptyListConstructor?.owner?.parent) {
            "Collection constructors must belong to the same linked KLIB class"
        }
    }
}

/**
 * Typed target representation for the collection operations left after common-body inlining.
 * Source API selection is by symbol identity only; helper names identify target runtime primitives.
 */
class KlibCollectionRuntimeRule(private val bindings: KlibCollectionRuntimeBindings) : CallRule, KlibPrimitiveBoundary {
    override val klibPrimitiveSymbols: Set<IrFunctionSymbol> = setOfNotNull(bindings.emptyListConstructor,
        bindings.iterator, bindings.hasNext, bindings.next, bindings.isEmpty, bindings.get, bindings.append,
        bindings.appendAll, bindings.capacityListConstructor, bindings.collectionSizeOrDefault,
        bindings.checkIndexOverflow)
    private val listClasses = listOfNotNull(bindings.emptyListConstructor?.owner?.parent as? IrClass).toSet()
    private val iterableClass = bindings.iterator.owner.parentAsClass.symbol
    private val collectionClasses = listOfNotNull(bindings.isEmpty, bindings.get, bindings.append, bindings.appendAll)
        .mapNotNull { it.collectionReceiverClass() }.toSet()

    override fun mapType(type: IrType, language: Language): EtsType? {
        val element = type.collectionElement(listClasses + iterableClass.owner + collectionClasses)
            ?: return null
        return EtsNamedType("Array", listOf(language.type(element)))
    }

    override fun lowerConstructor(call: IrConstructorCall, language: Language, scope: Scope): EtsExpression? {
        val emptyConstructor = bindings.emptyListConstructor
        val capacity = when {
            emptyConstructor != null && call.symbol === emptyConstructor -> false
            bindings.capacityListConstructor?.let { call.symbol === it } == true -> true
            else -> return null
        }
        if (call.valueArgumentsCount != (if (capacity) 1 else 0) ||
            call.dispatchReceiver != null || call.extensionReceiver != null) return null
        val listClass = emptyConstructor?.owner?.parentAsClass?.symbol ?: return null
        val element = call.type.collectionElement(setOf(listClass.owner), invariant = true) ?: return null
        if (call.typeArgumentsCount != listClass.owner.typeParameters.size ||
            (0 until call.typeArgumentsCount).any { call.getTypeArgument(it) == null } ||
            call.getTypeArgument(0) != element) return null
        val targetElement = language.type(element)
        if (language.type(call.type) != EtsNamedType("Array", listOf(targetElement))) return null
        val at = language.source(call)
        if (!capacity) return EtsArray(emptyList(), targetElement, at)
        val capacityExpression = call.getValueArgument(0) ?: return null
        if (language.type(capacityExpression.type) != EtsTypes.NUMBER) return null
        val value = language.expression(capacityExpression, scope)
        val parameter = EtsSymbol("klib-collection-capacity:${at.file}:${at.start}", "__etsCapacity", value.type, at)
        val result = EtsArray(emptyList(), targetElement, at)
        return EtsCall(EtsLambda(listOf(EtsParameter(parameter)), listOf(EtsReturn(result, at)), result.type, at),
            listOf(value), result.type, at)
    }

    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        val operation = when {
            call.symbol === bindings.iterator -> Operation.ITERATOR
            call.symbol === bindings.hasNext -> Operation.HAS_NEXT
            call.symbol === bindings.next -> Operation.NEXT
            bindings.isEmpty?.let { call.symbol === it } == true -> Operation.IS_EMPTY
            bindings.get?.let { call.symbol === it } == true -> Operation.GET
            bindings.append?.let { call.symbol === it } == true -> Operation.APPEND
            bindings.appendAll?.let { call.symbol === it } == true -> Operation.APPEND_ALL
            bindings.collectionSizeOrDefault?.let { call.symbol === it } == true -> Operation.SIZE_OR_DEFAULT
            bindings.checkIndexOverflow?.let { call.symbol === it } == true -> Operation.CHECK_INDEX_OVERFLOW
            else -> return null
        }
        val expectedTypeArguments = when (operation) {
            Operation.APPEND_ALL, Operation.SIZE_OR_DEFAULT -> 1
            else -> 0
        }
        if (call.superQualifierSymbol != null || call.typeArgumentsCount != expectedTypeArguments) return null
        val at = language.source(call)
        val result = language.type(call.type)
        if (operation == Operation.CHECK_INDEX_OVERFLOW) {
            if (call.dispatchReceiver != null || call.extensionReceiver != null || call.valueArgumentsCount != 1 ||
                result != EtsTypes.NUMBER) return null
            val valueExpression = call.getValueArgument(0) ?: return null
            if (language.type(valueExpression.type) != EtsTypes.NUMBER) return null
            val value = language.expression(valueExpression, scope)
            val parameter = EtsSymbol("klib-collection-index:${at.file}:${at.start}", "__etsIndex", EtsTypes.NUMBER, at)
            val reference = EtsReference(parameter)
            val negative = EtsBinary("<", reference, EtsLiteral(0, EtsTypes.NUMBER, at), EtsTypes.BOOLEAN, at)
            val message = EtsLiteral("Index overflow has happened.", EtsTypes.STRING, at)
            return EtsCall(EtsLambda(listOf(EtsParameter(parameter)), listOf(
                EtsIf(listOf(EtsBranch(negative,
                    listOf(EtsThrow(namedTargetFailure("ArithmeticException", at, message), at)))), at),
                EtsReturn(reference, at)), EtsTypes.NUMBER, at), listOf(value), EtsTypes.NUMBER, at)
        }
        val receiverExpression = call.dispatchReceiver ?: call.extensionReceiver ?: return null
        if (call.dispatchReceiver != null && call.extensionReceiver != null) return null
        val receiverType = language.type(receiverExpression.type)

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
            Operation.IS_EMPTY -> {
                if (call.valueArgumentsCount != 0 || receiverType.arrayElement() == null || result != EtsTypes.BOOLEAN)
                    return null
                val receiver = language.expression(receiverExpression, scope)
                val length = EtsMember(receiver, "length", EtsTypes.NUMBER, at)
                EtsBinary("===", length, EtsLiteral(0, EtsTypes.NUMBER, at), EtsTypes.BOOLEAN, at)
            }
            Operation.GET -> {
                if (call.valueArgumentsCount != 1) return null
                val element = receiverType.arrayElement()?.takeIf { it == result } ?: return null
                val indexExpression = call.getValueArgument(0) ?: return null
                if (language.type(indexExpression.type) != EtsTypes.NUMBER) return null
                val receiver = language.expression(receiverExpression, scope)
                val index = language.expression(indexExpression, scope)
                external("__etsListGet", listOf(receiver, index), result, at, listOf(element))
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
            Operation.APPEND_ALL -> {
                if (call.valueArgumentsCount != 1 || result != EtsTypes.BOOLEAN) return null
                val element = receiverType.arrayElement() ?: return null
                val typeArgument = call.getTypeArgument(0) ?: return null
                val valuesExpression = call.getValueArgument(0) ?: return null
                val valuesType = language.type(valuesExpression.type)
                if (language.type(typeArgument) != element || valuesType != EtsNamedType("Array", listOf(element)))
                    return null
                val receiver = language.expression(receiverExpression, scope)
                val values = language.expression(valuesExpression, scope)
                external("__etsListAddAll", listOf(receiver, values), result, at, listOf(element))
            }
            Operation.SIZE_OR_DEFAULT -> {
                if (call.valueArgumentsCount != 1 || result != EtsTypes.NUMBER) return null
                val element = receiverType.arrayElement() ?: return null
                val typeArgument = call.getTypeArgument(0) ?: return null
                val defaultExpression = call.getValueArgument(0) ?: return null
                if (language.type(typeArgument) != element || language.type(defaultExpression.type) != EtsTypes.NUMBER)
                    return null
                val receiver = language.expression(receiverExpression, scope)
                val default = language.expression(defaultExpression, scope)
                val receiverParameter = EtsSymbol("klib-collection-size:${at.file}:${at.start}:receiver",
                    "__etsValues", receiver.type, at)
                val defaultParameter = EtsSymbol("klib-collection-size:${at.file}:${at.start}:default",
                    "__etsDefault", default.type, at)
                val length = EtsMember(EtsReference(receiverParameter), "length", EtsTypes.NUMBER, at)
                EtsCall(EtsLambda(listOf(EtsParameter(receiverParameter), EtsParameter(defaultParameter)),
                    listOf(EtsReturn(length, at)), EtsTypes.NUMBER, at), listOf(receiver, default), EtsTypes.NUMBER, at)
            }
            Operation.CHECK_INDEX_OVERFLOW -> null
        }
    }

    private fun external(name: String, arguments: List<EtsExpression>, result: EtsType, at: SourceSpan,
        types: List<EtsType>): EtsExpression = EtsCall(
        EtsReference(EtsSymbol("stdlib:$name", name, EtsFunctionType(arguments.map { it.type }, result), at,
            external = true)), arguments, result, at, types)

    private enum class Operation {
        ITERATOR, HAS_NEXT, NEXT, IS_EMPTY, GET, APPEND, APPEND_ALL, SIZE_OR_DEFAULT, CHECK_INDEX_OVERFLOW
    }
}

private fun IrFunctionSymbol.collectionReceiverClass(): IrClass? =
    (owner.parent as? IrClass) ?: owner.extensionReceiverParameter?.type?.classOrNull?.owner

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
