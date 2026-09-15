@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.expressions.impl.IrCallImpl
import org.jetbrains.kotlin.ir.expressions.impl.IrGetValueImpl
import org.jetbrains.kotlin.ir.types.*
import org.jetbrains.kotlin.ir.util.*
import org.jetbrains.kotlin.ir.util.isNullable

internal object MapSetRules : CallRule {
    private val maps = setOf("kotlin.collections.Map", "kotlin.collections.MutableMap")
    private val sets = setOf("kotlin.collections.Set", "kotlin.collections.MutableSet")
    private val entries = setOf("kotlin.collections.Map.Entry", "kotlin.collections.MutableMap.MutableEntry")
    private fun name(type: IrType) = type.classOrNull?.owner?.let(::symbolName)
    override fun mapType(type: IrType, language: Language): EtsType? {
        val target = when (name(type)) {
            in maps -> "__etsMap"
            in sets -> "__etsSet"
            in entries -> "__etsMapEntry"
            "kotlin.Pair" -> "__etsPair"
            else -> return null
        }
        val args = (type as? IrSimpleType)?.arguments?.map { (it as? IrTypeProjection)?.type ?: return null } ?: return null
        return EtsNamedType(target, args.map(language::type), "stdlib:$target", external = true)
    }

    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        val owner = call.symbol.owner
        if (sourceFile(owner) != null || call.superQualifierSymbol != null) return null
        val original = if (owner.isFakeOverride) owner.collectRealOverrides().singleOrNull() ?: return null else owner
        val symbol = symbolName(original)
        val receiver = call.dispatchReceiver ?: call.extensionReceiver
        val at = language.source(call)
        fun lower(value: IrExpression) = language.expression(value, scope)
        fun args(): List<EtsExpression>? {
            return (0 until call.valueArgumentsCount).map { lower(call.getValueArgument(it) ?: return null) }
        }
        fun invoke(method: String, values: List<EtsExpression>, result: EtsType) = EtsCall(
            EtsMember(lower(receiver!!), method, EtsFunctionType(values.map { it.type }, result), at), values, result, at)
        val resultName = name(call.type)
        if (symbol == "kotlin.to" && resultName == "kotlin.Pair" && receiver != null && call.valueArgumentsCount == 1)
            return EtsNew(language.type(call.type) as EtsNamedType, listOf(lower(receiver)) + (args() ?: return null), at)
        val factories = setOf("kotlin.collections.mapOf", "kotlin.collections.mutableMapOf", "kotlin.collections.emptyMap",
            "kotlin.collections.setOf", "kotlin.collections.mutableSetOf", "kotlin.collections.emptySet")
        if (symbol in factories && receiver == null && resultName in maps + sets) {
            val types = (call.type as IrSimpleType).arguments.map { (it as IrTypeProjection).type }
            val values = (0 until call.valueArgumentsCount).flatMap { index ->
                when (val argument = call.getValueArgument(index)) {
                    null -> emptyList()
                    is IrVararg -> argument.elements.map { lower(it as? IrExpression ?: return null) }
                    else -> listOf(lower(argument))
                }
            }
            val key = types.first()
            val strategy = keyStrategy(key, language, scope, at)
            val element = if (resultName in maps) EtsNamedType("__etsPair", types.map(language::type), "stdlib:__etsPair", true)
                else language.type(key)
            val normalized = values.mapIndexed { index, value ->
                if (resultName !in maps || value.type == element) value
                else {
                    val pairType = value.type as? EtsNamedType ?: return null
                    if (pairType.symbolId != "stdlib:__etsPair" || pairType.arguments.size != 2) return null
                    val parameter = EtsSymbol("pair:${at.file}:${at.start}:$index", "pair", value.type, at)
                    val copied = EtsNew(element as EtsNamedType, listOf(
                        EtsMember(EtsReference(parameter), "first", pairType.arguments[0], at),
                        EtsMember(EtsReference(parameter), "second", pairType.arguments[1], at)), at)
                    EtsCall(EtsLambda(listOf(EtsParameter(parameter)), listOf(EtsReturn(copied, at)), element, at), listOf(value), element, at)
                }
            }
            return EtsNew(language.type(call.type) as EtsNamedType, strategy + EtsArray(normalized, element, at), at)
        }
        if (receiver == null) return null
        val receiverName = name(receiver.type)
        val memberName = original.correspondingPropertySymbol?.owner?.name?.asString() ?: original.name.asString()
        if (receiverName == "kotlin.Pair" && symbol.startsWith("kotlin.Pair.") && memberName in setOf("first", "second"))
            return EtsMember(lower(receiver), memberName, language.type(call.type), at)
        if (receiverName in entries && memberName in setOf("key", "value") && symbol.substringBeforeLast('.') in entries)
            return EtsMember(lower(receiver), memberName, language.type(call.type), at)
        if (receiverName in entries && symbol in setOf("kotlin.collections.component1", "kotlin.collections.component2"))
            return EtsMember(lower(receiver), if (memberName == "component1") "key" else "value", language.type(call.type), at)
        if (receiverName !in maps + sets || !symbol.startsWith("kotlin.collections.")) return null
        if (memberName == "size" && call.valueArgumentsCount == 0)
            return EtsMember(lower(receiver), "size", EtsTypes.NUMBER, at)
        if (memberName == "containsValue" && receiverName in maps && call.valueArgumentsCount == 1) {
            val valueType = (receiver.type as IrSimpleType).arguments[1].typeOrNull ?: return null
            return invoke("containsValue", (args() ?: return null) + keyStrategy(valueType, language, scope, at, false), EtsTypes.BOOLEAN)
        }
        val method = when (memberName) {
            "get", "put", "remove", "containsKey", "clear", "isEmpty", "iterator" -> memberName
            "add", "contains" -> if (receiverName in sets) memberName else return null
            "set" -> if (receiverName in maps) "put" else return null
            else -> return null
        }
        val values = args() ?: return null
        val result = if (memberName == "set") EtsNullableType(language.type((receiver.type as IrSimpleType).arguments[1].typeOrNull!!))
            else language.type(call.type)
        val invocation = invoke(method, values, result)
        return if (memberName == "set") etsDiscard(invocation, at) else invocation
    }
}

private fun keyStrategy(type: IrType, language: Language, scope: Scope, at: SourceSpan, includeHash: Boolean = true): List<EtsExpression> {
    val target = language.type(type)
    val left = EtsSymbol("key:${at.file}:${at.start}:left", "left", target, at)
    val right = EtsSymbol("key:${at.file}:${at.start}:right", "right", target, at)
    val lhs = EtsReference(left)
    val rhs = EtsReference(right)
    val plain = type.makeNotNull()
    fun same(a: EtsExpression, b: EtsExpression) = EtsBinary("===", a, b, EtsTypes.BOOLEAN, at)
    val nil = EtsLiteral(null, EtsTypes.NULL, at)
    fun member(methodName: String): EtsExpression {
        val owner = type.classOrNull?.owner
        val function = owner?.declarations?.filterIsInstance<IrSimpleFunction>()?.singleOrNull {
            it.name.asString() == methodName && it.valueParameters.size == if (methodName == "equals") 1 else 0
        } ?: throw Unsupported(Diagnostic("UNSUPPORTED", "Collection key requires resolved $methodName: ${type.render()}", at))
        val receiver = function.dispatchReceiverParameter!!
        val nested = scope.fork()
        nested.bindings[receiver.symbol] = EtsCast(lhs, language.type(plain), at)
        val call = IrCallImpl(at.start, at.end, function.returnType, function.symbol, 0).apply {
            dispatchReceiver = IrGetValueImpl(at.start, at.end, plain, receiver.symbol)
            function.valueParameters.singleOrNull()?.let {
                nested.bindings[it.symbol] = rhs
                putValueArgument(0, IrGetValueImpl(at.start, at.end, type, it.symbol))
            }
        }
        return language.expression(call, nested)
    }
    val equality = when {
        plain.isString() || plain.isBoolean() || plain.isInt() || plain.isShort() || plain.isByte() || plain.isChar() -> same(lhs, rhs)
        plain.isFloat() || plain.isDouble() -> same(EtsCall(EtsReference(EtsSymbol("stdlib:__etsFloatingCompare", "__etsFloatingCompare",
            EtsFunctionType(listOf(EtsTypes.NUMBER, EtsTypes.NUMBER), EtsTypes.NUMBER), at, true)),
            listOf(EtsCast(lhs, EtsTypes.NUMBER, at), EtsCast(rhs, EtsTypes.NUMBER, at)), EtsTypes.NUMBER, at), EtsLiteral(0, EtsTypes.NUMBER, at))
        sourceFile(type.classOrNull?.owner ?: throw Unsupported(Diagnostic("UNSUPPORTED", "Unsupported collection key type", at))) != null -> member("equals")
        else -> throw Unsupported(Diagnostic("UNSUPPORTED", "Collection key requires a supported equality representation: ${type.render()}", at))
    }
    val guardedEquality = if (type.isNullable()) EtsConditional(same(lhs, nil), same(rhs, nil),
        EtsConditional(same(rhs, nil), EtsLiteral(false, EtsTypes.BOOLEAN, at), equality, EtsTypes.BOOLEAN, at), EtsTypes.BOOLEAN, at) else equality
    val equalFunction = EtsLambda(listOf(EtsParameter(left), EtsParameter(right)), listOf(EtsReturn(guardedEquality, at)), EtsTypes.BOOLEAN, at)
    if (!includeHash) return listOf(equalFunction)
    val hash = member("hashCode")
    val guardedHash = if (type.isNullable()) EtsConditional(same(lhs, nil), EtsLiteral(0, EtsTypes.NUMBER, at), hash, EtsTypes.NUMBER, at) else hash
    return listOf(equalFunction,
        EtsLambda(listOf(EtsParameter(left)), listOf(EtsReturn(guardedHash, at)), EtsTypes.NUMBER, at))
}
