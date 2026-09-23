@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.expressions.IrConstructorCall
import org.jetbrains.kotlin.ir.types.IrType
import org.jetbrains.kotlin.ir.types.classFqName

private val snackbarHostStateSource = SourceSpan("EtsSnackbarHostState.kt", -1, -1)
internal val snackbarHostStateType = etsClassSymbol("EtsSnackbarHostState", snackbarHostStateSource).type as EtsNamedType

/** Target-owned identity for a host that has no active snackbar at component construction. */
internal class ComposeSnackbarHostStateRule : CallRule {
    override fun mapType(type: IrType, language: Language): EtsType? =
        if (type.classFqName?.asString() == "androidx.compose.material3.SnackbarHostState")
            snackbarHostStateType else null

    override fun lowerConstructor(call: IrConstructorCall, language: Language, scope: Scope): EtsExpression? {
        val parent = call.symbol.owner.parent as? org.jetbrains.kotlin.ir.declarations.IrClass ?: return null
        if (sourceFile(parent) != null || symbolName(parent) != "androidx.compose.material3.SnackbarHostState") return null
        if (call.valueArgumentsCount != 0)
            throw Unsupported(Diagnostic("UNSUPPORTED", "SnackbarHostState constructor requires no arguments",
                language.source(call)))
        return EtsNew(snackbarHostStateType, emptyList(), language.source(call))
    }

    override fun lower(call: org.jetbrains.kotlin.ir.expressions.IrCall, language: Language, scope: Scope): EtsExpression? = null

    override fun targetFiles(program: EtsProgram): List<EtsFile> {
        var used = false
        fun type(value: EtsType) {
            when (value) {
                is EtsNamedType -> {
                    if (value.symbolId == snackbarHostStateType.symbolId) used = true
                    value.arguments.forEach(::type)
                }
                is EtsNullableType -> type(value.inner)
                is EtsFunctionType -> { value.parameters.forEach(::type); type(value.result) }
                is EtsRecordType -> value.fields.values.forEach(::type)
                is EtsTupleType -> value.elements.forEach(::type)
                is EtsCapturedType -> { type(value.readType); type(value.writeType) }
                is EtsTypeParameterType -> Unit
            }
        }
        program.files.forEach { file -> file.declarations.forEach { declaration -> walkEts(declaration) { node ->
            when (node) {
                is EtsExpression -> type(node.type)
                is EtsFunction -> type(node.symbol.type)
                is EtsField -> type(node.symbol.type)
                is EtsGlobal -> type(node.symbol.type)
                is EtsVariable -> type(node.symbol.type)
                else -> Unit
            }
        } } }
        if (!used) return emptyList()
        val constructor = EtsFunction("constructor", emptyList(), EtsTypes.VOID, emptyList(), snackbarHostStateSource,
            kind = EtsFunctionKind.CONSTRUCTOR)
        return listOf(EtsFile(snackbarHostStateSource.file!!, listOf(EtsClass(snackbarHostStateType.name,
            listOf(constructor), snackbarHostStateSource, exported = true, valueSnapshot = true))))
    }
}
