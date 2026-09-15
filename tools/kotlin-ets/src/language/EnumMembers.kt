@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.*
import org.jetbrains.kotlin.ir.util.*

internal fun enumClassReference(owner: IrClass, language: Language, at: SourceSpan): EtsReference {
    val type = language.type(owner.defaultType) as EtsNamedType
    val declaration = SourceSpan(sourceFile(owner)?.fileEntry?.name, owner.startOffset, owner.endOffset)
    return EtsReference(etsClassSymbol(type.name, declaration, sourceName = owner.name.asString()), at)
}

internal fun enumEntryReference(entry: IrEnumEntry, language: Language, at: SourceSpan): EtsExpression =
    EtsMember(enumClassReference(entry.parentAsClass, language, at), entry.name.asString(),
        language.type(entry.parentAsClass.defaultType), at)

/** Kotlin/JS likewise keeps enum objects and lazy entry access, not integer tags. */
internal fun enumMembers(owner: IrClass, language: Language, construct: (IrEnumEntry, Int) -> EtsExpression): List<EtsClassMember> {
    val at = language.source(owner)
    val type = language.type(owner.defaultType)
    val array = EtsNamedType("Array", listOf(type))
    val reference = enumClassReference(owner, language, at)
    val entries = owner.declarations.filterIsInstance<IrEnumEntry>()
    fun literal(value: Int) = EtsLiteral(value, EtsTypes.NUMBER, at)
    fun string(value: String) = EtsLiteral(value, EtsTypes.STRING, at)
    fun field(name: String, type: EtsType) = EtsSymbol("enum:${at.file}:${at.start}:$name", name, type, at)
    fun access(symbol: EtsSymbol) = EtsMember(reference, symbol.name, symbol.type, at, symbol.id)
    fun assign(target: EtsExpression, value: EtsExpression) = EtsExpressionStatement(EtsAssignment(target, value, at))
    val state = field("__etsEnumState", EtsTypes.NUMBER)
    val stored = field("__etsEnumEntries", array)
    val slots = entries.map { field("__ets" + it.name.asString(), EtsNullableType(type)) }
    val initialization = entries.mapIndexed { index, entry -> assign(access(slots[index]), construct(entry, index)) } +
        assign(access(stored), EtsArray(slots.map { EtsCast(access(it), type, at) }, type, at)) + assign(access(state), literal(2))
    val failure = EtsSymbol("enum:${at.file}:${at.start}:failure", "failure", EtsTypes.OBJECT, at)
    val init = EtsFunction("__etsInitEnum", emptyList(), EtsTypes.VOID, listOf(
        EtsIf(listOf(EtsBranch(EtsBinary("===", access(state), literal(3), EtsTypes.BOOLEAN, at),
            listOf(EtsThrow(namedTargetFailure("NoClassDefFoundError", at), at)))), at),
        EtsIf(listOf(EtsBranch(EtsBinary("!==", access(state), literal(0), EtsTypes.BOOLEAN, at),
            listOf(EtsReturn(null, at)))), at),
        assign(access(state), literal(1)),
        EtsTry(initialization, EtsCatch(failure, listOf(assign(access(state), literal(3)),
            EtsThrow(namedTargetFailure("ExceptionInInitializerError", at), at))), emptyList(), at)
    ), at, kind = EtsFunctionKind.METHOD, static = true, visibility = EtsVisibility.PRIVATE)
    val initialize = EtsExpressionStatement(EtsCall(EtsMember(reference, init.name, init.symbol.type, at), emptyList(), EtsTypes.VOID, at))
    val members = mutableListOf<EtsClassMember>(
        EtsField(field("name", EtsTypes.STRING), readonly = true),
        EtsField(field("ordinal", EtsTypes.NUMBER), readonly = true),
        EtsField(state, literal(0), EtsVisibility.PRIVATE, static = true),
        EtsField(stored, EtsArray(emptyList(), type, at), EtsVisibility.PRIVATE, static = true), init)
    if (owner.declarations.filterIsInstance<IrSimpleFunction>().none { it.name.asString() == "toString" && !it.isFakeOverride }) {
        val self = EtsReference(EtsSymbol("enum:${at.file}:${at.start}:this", "this", type, at, external = true))
        members.add(EtsFunction("toString", emptyList(), EtsTypes.STRING,
            listOf(EtsReturn(EtsMember(self, "name", EtsTypes.STRING, at), at)), at, kind = EtsFunctionKind.METHOD))
    }
    slots.forEach { members.add(EtsField(it, EtsLiteral(null, EtsTypes.NULL, at), EtsVisibility.PRIVATE, static = true)) }
    entries.forEachIndexed { index, entry -> members.add(EtsFunction(entry.name.asString(), emptyList(), type,
        listOf(initialize, EtsReturn(EtsCast(access(slots[index]), type, at), at)), language.source(entry),
        kind = EtsFunctionKind.GETTER, static = true)) }
    members.add(EtsFunction("values", emptyList(), array, listOf(initialize,
        EtsReturn(EtsCall(EtsMember(access(stored), "slice", EtsFunctionType(emptyList(), array), at), emptyList(), array, at), at)),
        at, kind = EtsFunctionKind.METHOD, static = true))
    members.add(EtsFunction("entries", emptyList(), array, listOf(initialize, EtsReturn(access(stored), at)),
        at, kind = EtsFunctionKind.GETTER, static = true))
    val name = field("value", EtsTypes.STRING)
    members.add(EtsFunction("valueOf", listOf(EtsParameter(name)), type, listOf(initialize) +
        entries.mapIndexed { index, entry -> EtsIf(listOf(EtsBranch(EtsBinary("===", EtsReference(name), string(entry.name.asString()), EtsTypes.BOOLEAN, at),
            listOf(EtsReturn(EtsCast(access(slots[index]), type, at), at)))), at) } +
        EtsThrow(namedTargetFailure("IllegalArgumentException", at), at), at, kind = EtsFunctionKind.METHOD, static = true))
    return members
}
