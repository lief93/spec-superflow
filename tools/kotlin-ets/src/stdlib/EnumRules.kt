@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.descriptors.ClassKind
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.*
import org.jetbrains.kotlin.ir.util.*

internal object EnumRules {
    fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        val owner = call.symbol.owner
        val parent = owner.parent as? IrClass
        val at = language.source(call)
        val receiver = call.dispatchReceiver
        if (parent?.kind == ClassKind.ENUM_CLASS && owner.body is IrSyntheticBody && receiver == null) {
            val result = language.type(call.type)
            val klass = enumClassReference(parent, language, at)
            if (owner.correspondingPropertySymbol?.owner?.name?.asString() == "entries")
                return EtsMember(klass, "entries", result, at)
            if (owner.name.asString() !in setOf("values", "valueOf")) return null
            val args = (0 until call.valueArgumentsCount).map { language.expression(call.getValueArgument(it) ?: return null, scope) }
            return EtsCall(EtsMember(klass, owner.name.asString(), EtsFunctionType(args.map { it.type }, result), at), args, result, at)
        }
        if (receiver == null) return null
        val original = if (owner.isFakeOverride) owner.collectRealOverrides().singleOrNull() ?: return null else owner
        val origin = (original.parent as? IrClass)?.fqNameWhenAvailable?.asString()
        if (origin != "kotlin.Enum" || receiver.type.classOrNull?.owner?.kind != ClassKind.ENUM_CLASS) return null
        val result = language.type(call.type)
        val value = language.expression(receiver, scope)
        val property = original.correspondingPropertySymbol?.owner?.name?.asString()
        if (property in setOf("name", "ordinal")) return EtsMember(value, property!!, result, at)
        return when (owner.name.asString()) {
            "toString" -> EtsMember(value, "name", EtsTypes.STRING, at)
            "hashCode" -> EtsMember(value, "ordinal", EtsTypes.NUMBER, at)
            "equals" -> EtsBinary("===", value, language.expression(call.getValueArgument(0) ?: return null, scope), EtsTypes.BOOLEAN, at)
            "compareTo" -> EtsBinary("-", EtsMember(value, "ordinal", EtsTypes.NUMBER, at),
                EtsMember(language.expression(call.getValueArgument(0) ?: return null, scope), "ordinal", EtsTypes.NUMBER, at), EtsTypes.NUMBER, at)
            else -> null
        }
    }
}
