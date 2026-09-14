@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.declarations.IrClass
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.*
import org.jetbrains.kotlin.ir.types.impl.makeTypeProjection
import org.jetbrains.kotlin.ir.util.*
import org.jetbrains.kotlin.ir.util.isNullable
import org.jetbrains.kotlin.types.Variance

internal object IterationRules : CallRule {
    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        val name = symbolName(call.symbol.owner)
        if (name !in supportedNames || !resolvedSignature(call)) return null
        val receiver = call.dispatchReceiver ?: call.extensionReceiver
        val receiverName = receiver?.type.className()
        val source = language.source(call)
        fun lower(value: IrExpression) = language.expression(value, scope)
        fun target() = lower(checkNotNull(receiver))
        fun literal(value: Any, type: EtsType) = EtsLiteral(value, type, source)
        fun runtime(name: String, values: List<EtsExpression>, result: EtsType,
            types: List<EtsType> = emptyList()): EtsExpression = EtsCall(EtsReference(EtsSymbol("stdlib:$name", name,
                EtsFunctionType(values.map { it.type }, result), source, external = true)), values, result, source, types)
        fun property(name: String) = EtsMember(target(), name, EtsTypes.NUMBER, source)
        fun method(name: String, result: EtsType) = EtsCall(EtsMember(target(), name,
            EtsFunctionType(emptyList(), result), source), emptyList(), result, source)
        val element = receiver?.type?.element()
        val array = receiverName in arrayTypes
        val list = receiverName in listTypes
        val iterator = receiverName in iteratorTypes
        val progression = receiverName in progressionTypes

        if (name in factories && receiver == null && call.valueArgumentsCount == 1) {
            val argument = call.getValueArgument(0)
            val values = if (argument == null) null else argument as? IrVararg ?: return null
            if (values?.elements?.any { it !is IrExpression } == true) return null
            val resultElement = call.type.element() ?: return null
            if (values != null && values.varargElementType != resultElement) return null
            return EtsArray(values?.elements.orEmpty().map { lower(it as IrExpression) }, language.type(resultElement), source)
        }
        val args = (0 until call.valueArgumentsCount).map { checkNotNull(call.getValueArgument(it)) }
        if (name in arraySizes && array && args.isEmpty() && call.type.isInt()) return property("length")
        if (name in arrayGets && array && args.size == 1 && args[0].type.isInt() && call.type == element) {
            val mapped = language.type(checkNotNull(element))
            return runtime("__etsArrayGet", listOf(target(), lower(args[0])), mapped, listOf(mapped))
        }
        if (name in arraySets && array && args.size == 2 && args[0].type.isInt() &&
            args[1].type == element && call.type.isUnit()) {
            val mapped = language.type(checkNotNull(element))
            return runtime("__etsArraySet", listOf(target(), lower(args[0]), lower(args[1])), EtsTypes.VOID, listOf(mapped))
        }
        if (name in iterators && (list || array) && element != null && args.isEmpty() &&
            call.type.className() in iteratorTypes && call.type.element() == element) {
            val mapped = language.type(element)
            return runtime("__etsArrayIterator", listOf(target(), literal(list, EtsTypes.BOOLEAN)),
                language.type(call.type), listOf(mapped))
        }
        if (name in iteratorHasNext && iterator && args.isEmpty() && call.type.isBoolean()) {
            return method("hasNext", EtsTypes.BOOLEAN)
        }
        if (name in iteratorNext && iterator && args.isEmpty() && call.type == element) {
            return method("next", language.type(call.type))
        }
        if (name in progressionIterators && progression && args.isEmpty() &&
            call.type.className() == "kotlin.collections.IntIterator") {
            return runtime("__etsProgressionIterator", listOf(target()), language.type(call.type))
        }
        if (name in progressionProperties && progression && args.isEmpty() && call.type.isInt()) {
            return property(progressionProperties.getValue(name))
        }
        if (name in ranges && receiverName == "kotlin.Int" && args.size == 1 && args[0].type.isInt() &&
            call.type.className() == ranges.getValue(name)) {
            val inputs = listOf(target(), lower(args[0]))
            if (name == "kotlin.ranges.until") return runtime("__etsIntUntil", inputs, language.type(call.type))
            return runtime("__etsIntProgressionCreate", inputs + literal(if (name == "kotlin.ranges.downTo") -1 else 1,
                EtsTypes.NUMBER), language.type(call.type))
        }
        if (name == "kotlin.ranges.step" && progression && args.size == 1 && args[0].type.isInt() &&
            call.type.className() == "kotlin.ranges.IntProgression") {
            return runtime("__etsIntStep", listOf(target(), lower(args[0])), language.type(call.type))
        }
        if (name == "kotlin.ranges.reversed" && progression && args.isEmpty() &&
            call.type.className() == "kotlin.ranges.IntProgression") {
            return runtime("__etsIntReverse", listOf(target()), language.type(call.type))
        }
        return null
    }
}

private val arrayTypes = setOf("kotlin.Array", "kotlin.IntArray")
private val listTypes = setOf("kotlin.collections.List", "kotlin.collections.MutableList", "kotlin.collections.Iterable")
private val iteratorTypes = setOf("kotlin.collections.Iterator", "kotlin.collections.MutableIterator", "kotlin.collections.IntIterator")
private val progressionTypes = setOf("kotlin.ranges.IntRange", "kotlin.ranges.IntProgression")
private val factories = setOf("kotlin.arrayOf", "kotlin.intArrayOf")
private val arraySizes = arrayTypes.map { "$it.<get-size>" }.toSet()
private val arrayGets = arrayTypes.map { "$it.get" }.toSet()
private val arraySets = arrayTypes.map { "$it.set" }.toSet()
private val iterators = (arrayTypes + listTypes).map { "$it.iterator" }.toSet()
private val iteratorHasNext = iteratorTypes.map { "$it.hasNext" }.toSet()
private val iteratorNext = setOf("kotlin.collections.Iterator.next", "kotlin.collections.MutableIterator.next",
    "kotlin.collections.IntIterator.next", "kotlin.collections.IntIterator.nextInt")
private val progressionIterators = progressionTypes.map { "$it.iterator" }.toSet()
private val progressionProperties = progressionTypes.flatMap { type ->
    listOf("first", "last", "step").map { "$type.<get-$it>" to it }
}.toMap()
private val ranges = mapOf("kotlin.Int.rangeTo" to "kotlin.ranges.IntRange", "kotlin.ranges.until" to "kotlin.ranges.IntRange",
    "kotlin.ranges.downTo" to "kotlin.ranges.IntProgression")
private val supportedNames = factories + arraySizes + arrayGets + arraySets + iterators + iteratorHasNext + iteratorNext +
    progressionIterators + progressionProperties.keys + ranges.keys + setOf("kotlin.ranges.step", "kotlin.ranges.reversed")

private fun IrType?.className(): String? = (this as? IrSimpleType)?.takeUnless { it.isNullable() }
    ?.classOrNull?.owner?.fqNameWhenAvailable?.asString()

private fun IrType.element(): IrType? = when (className()) {
    "kotlin.IntArray", "kotlin.collections.IntIterator" -> classOrNull!!.owner.let { klass ->
        klass.declarations.filterIsInstance<org.jetbrains.kotlin.ir.declarations.IrSimpleFunction>()
            .firstOrNull { it.name.asString() == if (className() == "kotlin.IntArray") "get" else "nextInt" }?.returnType
    }
    in arrayTypes + listTypes + iteratorTypes -> ((this as IrSimpleType).arguments.singleOrNull() as? IrTypeProjection)
        ?.takeIf { it.variance == Variance.INVARIANT }?.type
    else -> null
}

// Substitute official declaration type parameters with the actual receiver/call arguments.
// Exact supported symbol names above include only the observed standard-library fake overrides.
private fun resolvedSignature(call: IrCall): Boolean {
    val owner = call.symbol.owner
    if (sourceFile(owner) != null || owner.isSuspend || call.superQualifierSymbol != null ||
        (owner.dispatchReceiverParameter == null) != (call.dispatchReceiver == null) ||
        (owner.extensionReceiverParameter == null) != (call.extensionReceiver == null) ||
        owner.valueParameters.size != call.valueArgumentsCount || owner.typeParameters.size != call.typeArgumentsCount ||
        owner.valueParameters.any { it.defaultValue != null } ||
        (0 until call.typeArgumentsCount).any { call.getTypeArgument(it) == null }) return false
    val receiver = call.dispatchReceiver
    if (receiver != null) {
        val type = receiver.type as? IrSimpleType ?: return false
        if (type.isNullable() || type.arguments.any { it !is IrTypeProjection || it.variance != Variance.INVARIANT }) return false
        val parent = owner.parent as? IrClass ?: return false
        if (type.arguments.size != parent.typeParameters.size) return false
        val parentName = parent.fqNameWhenAvailable?.asString()
        if (type.className() != parentName &&
            !(type.className() == "kotlin.ranges.IntRange" && parentName == "kotlin.ranges.IntProgression")) return false
    }
    val substitutor = IrTypeSubstitutor(call.getTypeSubstitutionMap(owner).mapValues {
        makeTypeProjection(it.value, Variance.INVARIANT)
    }, allowEmptySubstitution = true)
    if (substitutor.substitute(owner.returnType) != call.type) return false
    if (receiver != null) {
        val declared = substitutor.substitute(owner.dispatchReceiverParameter!!.type)
        if (receiver.type != declared && !inheritedReceiver(receiver.type, declared, owner.isFakeOverride)) return false
    }
    val extension = call.extensionReceiver
    if (extension != null) {
        val declared = substitutor.substitute(owner.extensionReceiverParameter!!.type)
        if (extension.type != declared && !(extension.type.className() == "kotlin.ranges.IntRange" &&
            declared.className() == "kotlin.ranges.IntProgression")) return false
    }
    return owner.valueParameters.indices.all { index ->
        val value = call.getValueArgument(index)
        val parameter = owner.valueParameters[index]
        if (parameter.varargElementType != null) {
            val element = substitutor.substitute(parameter.varargElementType!!)
            val container = substitutor.substitute(parameter.type) as? IrSimpleType ?: return false
            val shape = when (symbolName(owner)) {
                "kotlin.arrayOf" -> container.className() == "kotlin.Array" &&
                    (container.arguments.singleOrNull() as? IrTypeProjection)?.let {
                        it.variance == Variance.OUT_VARIANCE && it.type == element
                    } == true
                "kotlin.intArrayOf" -> container.className() == "kotlin.IntArray" &&
                    container.arguments.isEmpty() && element.isInt()
                else -> false
            }
            shape && (value == null || value is IrVararg && value.type == container && value.varargElementType == element)
        } else value != null && value.type == substitutor.substitute(parameter.type)
    }
}

private fun inheritedReceiver(actual: IrType, declared: IrType, fakeOverride: Boolean): Boolean {
    val from = actual as? IrSimpleType ?: return false
    val to = declared as? IrSimpleType ?: return false
    if (from.className() == "kotlin.ranges.IntRange" && to.className() == "kotlin.ranges.IntProgression") {
        return from.arguments.isEmpty() && to.arguments.isEmpty()
    }
    if (!fakeOverride) return false
    return when (from.className() to to.className()) {
        "kotlin.collections.MutableList" to "kotlin.collections.MutableCollection",
        "kotlin.collections.MutableIterator" to "kotlin.collections.Iterator" -> from.arguments == to.arguments
        "kotlin.collections.IntIterator" to "kotlin.collections.Iterator" ->
            from.arguments.isEmpty() && to.element()?.isInt() == true
        else -> false
    }
}
