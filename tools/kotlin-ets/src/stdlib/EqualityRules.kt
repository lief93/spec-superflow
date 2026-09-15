@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.IrBuiltIns
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.expressions.impl.IrCallImpl
import org.jetbrains.kotlin.ir.expressions.impl.IrGetValueImpl
import org.jetbrains.kotlin.ir.types.*
import org.jetbrains.kotlin.ir.util.*
import org.jetbrains.kotlin.ir.util.isNullable

internal object EqualityRules {
    fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        val owner = call.symbol.owner
        val at = language.source(call)
        val name = symbolName(owner)
        fun lower(value: IrExpression) = language.expression(value, scope)
        fun same(left: EtsExpression, right: EtsExpression) = EtsBinary("===", left, right, EtsTypes.BOOLEAN, at)
        if (owner.origin == IrBuiltIns.BUILTIN_OPERATOR && call.valueArgumentsCount == 1 && name in setOf(
            "kotlin.internal.ir.dataClassArrayMemberHashCode", "kotlin.internal.ir.dataClassArrayMemberToString")) {
            val array = call.getValueArgument(0) ?: return null
            if (!array.type.makeNotNull().isIntArray()) return null
            val hash = name.endsWith("HashCode")
            val helper = if (hash) "__etsIntArrayHash" else "__etsIntArrayString"
            val result = if (hash) EtsTypes.NUMBER else EtsTypes.STRING
            return EtsCall(EtsReference(EtsSymbol("stdlib:$helper", helper,
                EtsFunctionType(listOf(language.type(array.type)), result), at, external = true)),
                listOf(lower(array)), result, at)
        }
        if (owner.origin == IrBuiltIns.BUILTIN_OPERATOR && call.valueArgumentsCount == 2 &&
            name in setOf("kotlin.internal.ir.EQEQ", "kotlin.internal.ir.EQEQEQ")) {
            val left = call.getValueArgument(0) ?: return null
            val right = call.getValueArgument(1) ?: return null
            if (name.endsWith(".EQEQEQ") || left is IrConst && left.kind == IrConstKind.Null ||
                right is IrConst && right.kind == IrConstKind.Null) return same(lower(left), lower(right))
            val primitive = left.type.makeNotNull()
            if (primitive == right.type && !left.type.isNullable() && (primitive.isFloat() || primitive.isDouble())) {
                val compare = EtsCall(EtsReference(EtsSymbol("stdlib:__etsFloatingCompare", "__etsFloatingCompare",
                    EtsFunctionType(listOf(EtsTypes.NUMBER, EtsTypes.NUMBER), EtsTypes.NUMBER), at, external = true)),
                    listOf(lower(left), lower(right)), EtsTypes.NUMBER, at)
                return same(compare, EtsLiteral(0, EtsTypes.NUMBER, at))
            }
            if (primitive.isArray() || primitive.isPrimitiveArray()) return same(lower(left), lower(right))
            if (primitive == right.type.makeNotNull() && (primitive.isString() || primitive.isBoolean() ||
                primitive.isInt() || primitive.isByte() || primitive.isShort() || primitive.isChar()))
                return same(lower(left), lower(right))
            val klass = left.type.classOrNull?.owner ?: return null
            if (klass.kind == org.jetbrains.kotlin.descriptors.ClassKind.ENUM_CLASS) return same(lower(left), lower(right))
            if (sourceFile(klass) == null) return null
            val method = klass.declarations.filterIsInstance<IrSimpleFunction>().singleOrNull {
                it.name.asString() == "equals" && it.valueParameters.size == 1 && it.valueParameters[0].type.isNullableAny()
            } ?: return null
            val implementation = if (method.isFakeOverride) method.collectRealOverrides().singleOrNull() ?: return null else method
            if (symbolName(implementation) == "kotlin.Any.equals") return same(lower(left), lower(right))
            fun invocation(receiver: IrExpression, other: IrExpression, nested: Scope) = language.expression(
                IrCallImpl(call.startOffset, call.endOffset, owner.returnType, implementation.symbol, 0).apply {
                    dispatchReceiver = receiver
                    putValueArgument(0, other)
                }, nested)
            if (!left.type.isNullable()) return invocation(left, right, scope)
            // Both operands evaluate once, even when the left operand is null.
            val lhs = EtsSymbol("eq:${at.file}:${at.start}:left", "left", language.type(left.type), at)
            val rhs = EtsSymbol("eq:${at.file}:${at.start}:right", "right", language.type(right.type), at)
            val receiver = implementation.dispatchReceiverParameter!!
            val other = implementation.valueParameters.single()
            val nested = scope.fork()
            nested.bindings[receiver.symbol] = EtsCast(EtsReference(lhs), language.type(left.type.makeNotNull()), at)
            nested.bindings[other.symbol] = EtsReference(rhs)
            val body = EtsConditional(same(EtsReference(lhs), EtsLiteral(null, EtsTypes.NULL, at)),
                same(EtsReference(rhs), EtsLiteral(null, EtsTypes.NULL, at)),
                invocation(IrGetValueImpl(call.startOffset, call.endOffset, receiver.type, receiver.symbol),
                    IrGetValueImpl(call.startOffset, call.endOffset, other.type, other.symbol), nested), EtsTypes.BOOLEAN, at)
            return EtsCall(EtsLambda(listOf(EtsParameter(lhs), EtsParameter(rhs)), listOf(EtsReturn(body, at)),
                EtsTypes.BOOLEAN, at), listOf(lower(left), lower(right)), EtsTypes.BOOLEAN, at)
        }
        val receiver = call.dispatchReceiver ?: return null
        if (owner.name.asString() == "equals" && call.valueArgumentsCount == 1) {
            val original = if (owner.isFakeOverride) owner.collectRealOverrides().singleOrNull() ?: return null else owner
            if (symbolName(original) == "kotlin.Any.equals" && receiver.type.classOrNull?.owner?.let(::sourceFile) != null)
                return same(lower(receiver), lower(call.getValueArgument(0) ?: return null))
        }
        if (owner.name.asString() == "hashCode" && call.valueArgumentsCount == 0) {
            val original = if (owner.isFakeOverride) owner.collectRealOverrides().singleOrNull() ?: return null else owner
            if (sourceFile(original) != null) return null
            val receiverType = receiver.type.makeNotNull()
            val value = if (receiver.type.isNullable()) EtsCast(lower(receiver), language.type(receiverType), at) else lower(receiver)
            return when {
                receiverType.isInt() || receiverType.isByte() || receiverType.isShort() -> value
                receiverType.isBoolean() -> EtsConditional(value, EtsLiteral(1231, EtsTypes.NUMBER, at),
                    EtsLiteral(1237, EtsTypes.NUMBER, at), EtsTypes.NUMBER, at)
                receiverType.isString() -> {
                    val symbol = EtsSymbol("stdlib:__etsStringHash", "__etsStringHash",
                        EtsFunctionType(listOf(EtsTypes.STRING), EtsTypes.NUMBER), at, external = true)
                    EtsCall(EtsReference(symbol), listOf(value), EtsTypes.NUMBER, at)
                }
                receiverType.isChar() -> EtsCall(EtsMember(value, "charCodeAt",
                    EtsFunctionType(listOf(EtsTypes.NUMBER), EtsTypes.NUMBER), at),
                    listOf(EtsLiteral(0, EtsTypes.NUMBER, at)), EtsTypes.NUMBER, at)
                receiverType.isFloat() || receiverType.isDouble() -> {
                    val helper = if (receiverType.isFloat()) "__etsFloatHash" else "__etsDoubleHash"
                    EtsCall(EtsReference(EtsSymbol("stdlib:$helper", helper,
                        EtsFunctionType(listOf(EtsTypes.NUMBER), EtsTypes.NUMBER), at, external = true)),
                        listOf(value), EtsTypes.NUMBER, at)
                }
                receiver.type.classOrNull?.owner?.let(::sourceFile) != null -> EtsCall(EtsMember(value, "hashCode",
                    EtsFunctionType(emptyList(), EtsTypes.NUMBER), at), emptyList(), EtsTypes.NUMBER, at)
                else -> null
            }
        }
        return null
    }
}
