@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.*

private val builderSource = SourceSpan("EtsStringBuilder.kt", 0, 0)
private val builderType = etsClassSymbol("EtsStringBuilder", builderSource).type as EtsNamedType

/** JVM StringBuilder calls share one mutable native string-array representation. */
internal object StringBuilderRule : CallRule {
    override fun mapType(type: IrType, language: Language): EtsType? =
        if (type.classOrNull?.owner?.let(::symbolName) == "java.lang.StringBuilder") builderType else null

    override fun lowerConstructor(call: IrConstructorCall, language: Language, scope: Scope): EtsExpression? {
        if (mapType(call.type, language) == null) return null
        val initial = when (call.valueArgumentsCount) {
            0 -> EtsLiteral("", EtsTypes.STRING, language.source(call))
            1 -> call.getValueArgument(0)?.takeIf { it.type.isString() }?.let { language.expression(it, scope) } ?: return null
            else -> return null
        }
        return EtsNew(builderType, listOf(initial), language.source(call))
    }

    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        val receiver = call.dispatchReceiver ?: return null
        if (mapType(receiver.type, language) == null || sourceFile(call.symbol.owner) != null) return null
        val owner = call.symbol.owner
        if (!symbolName(owner).startsWith("java.lang.")) return null
        val at = language.source(call)
        val result: EtsType
        val args: List<EtsExpression>
        when (owner.name.asString()) {
            "append" -> {
                if (call.valueArgumentsCount != 1 || mapType(call.type, language) == null) return null
                val input = call.getValueArgument(0) ?: return null
                val plain = input.type.makeNotNull()
                if (!plain.isString() && !plain.isChar()) return null
                args = listOf(EtsBinary("+", EtsLiteral("", EtsTypes.STRING, at), language.expression(input, scope), EtsTypes.STRING, at))
                result = builderType
            }
            "toString" -> {
                if (call.valueArgumentsCount != 0 || !call.type.isString()) return null
                args = emptyList()
                result = EtsTypes.STRING
            }
            else -> return null
        }
        return EtsCall(EtsMember(language.expression(receiver, scope), owner.name.asString(),
            EtsFunctionType(args.map { it.type }, result), at), args, result, at)
    }

    override fun targetFiles(program: EtsProgram): List<EtsFile> {
        var used = false
        program.files.forEach { it.declarations.forEach { declaration -> walkEts(declaration) {
            if (it is EtsNew && it.type == builderType) used = true
        } } }
        if (!used) return emptyList()
        val at = builderSource
        val chunks = EtsSymbol("stringBuilder:chunks", "chunks", EtsNamedType("Array", listOf(EtsTypes.STRING)), at)
        val self = EtsReference(EtsSymbol("stringBuilder:this", "this", builderType, at, external = true))
        val storage = EtsMember(self, chunks.name, chunks.type, at, chunks.id)
        val value = EtsParameter(EtsSymbol("stringBuilder:value", "value", EtsTypes.STRING, at))
        val input = EtsReference(value.symbol)
        val constructor = EtsFunction("constructor", listOf(value), EtsTypes.VOID, listOf(EtsExpressionStatement(
            EtsAssignment(storage, EtsArray(listOf(input), EtsTypes.STRING, at), at))), at, kind = EtsFunctionKind.CONSTRUCTOR)
        val append = EtsFunction("append", listOf(value), builderType, listOf(
            EtsExpressionStatement(EtsCall(EtsMember(storage, "push", EtsFunctionType(listOf(EtsTypes.STRING), EtsTypes.NUMBER), at),
                listOf(input), EtsTypes.NUMBER, at)), EtsReturn(self, at)), at, kind = EtsFunctionKind.METHOD)
        val render = EtsFunction("toString", emptyList(), EtsTypes.STRING, listOf(EtsReturn(
            EtsCall(EtsMember(storage, "join", EtsFunctionType(listOf(EtsTypes.STRING), EtsTypes.STRING), at),
                listOf(EtsLiteral("", EtsTypes.STRING, at)), EtsTypes.STRING, at), at)), at, kind = EtsFunctionKind.METHOD)
        return listOf(EtsFile(at.file!!, listOf(EtsClass(builderType.name,
            listOf(EtsField(chunks, visibility = EtsVisibility.PRIVATE), constructor, append, render), at, exported = true))))
    }
}
