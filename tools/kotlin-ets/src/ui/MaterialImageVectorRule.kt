@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.types.classFqName

private val imageVectorSource = SourceSpan("EtsImageVector.kt", -1, -1)
internal val materialImageVectorType = etsClassSymbol("EtsImageVector", imageVectorSource).type as EtsNamedType
internal val materialImageVectorResourceType = EtsNamedType("Resource", external = true)

/** Maps explicitly known Material vector identities to equivalent Harmony system symbols. */
internal class ComposeMaterialImageVectorRule : CallRule {
    override fun mapType(type: org.jetbrains.kotlin.ir.types.IrType, language: Language): EtsType? =
        if (type.classFqName?.asString() == "androidx.compose.ui.graphics.vector.ImageVector")
            materialImageVectorType else null

    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        val owner = call.symbol.owner
        if (sourceFile(owner) != null || call.type.classFqName?.asString() !=
            "androidx.compose.ui.graphics.vector.ImageVector") return null
        val property = owner.correspondingPropertySymbol?.owner?.let(::symbolName) ?: symbolName(owner)
        val symbol = when (property) {
            "androidx.compose.material.icons.filled.Menu",
            "androidx.compose.material.icons.filled.<get-Menu>" -> "sys.symbol.line_3_horizontal"
            else -> return null
        }
        val at = language.source(call)
        val resource = EtsCall(EtsReference(EtsSymbol("arkui:resource", "\$r",
            EtsFunctionType(listOf(EtsTypes.STRING), materialImageVectorResourceType), at, external = true)),
            listOf(EtsLiteral(symbol, EtsTypes.STRING, at)), materialImageVectorResourceType, at)
        return EtsNew(materialImageVectorType, listOf(resource), at)
    }

    override fun targetFiles(program: EtsProgram): List<EtsFile> {
        var used = false
        fun type(value: EtsType) {
            when (value) {
                is EtsNamedType -> {
                    if (value.symbolId == materialImageVectorType.symbolId) used = true
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
        val at = imageVectorSource
        val field = EtsSymbol("compose:image-vector:resource", "resource", materialImageVectorResourceType, at)
        val parameter = EtsParameter(EtsSymbol("compose:image-vector:parameter", "resource",
            materialImageVectorResourceType, at))
        val self = EtsReference(EtsSymbol("material-image-vector:this", "this", materialImageVectorType,
            at, external = true))
        val constructor = EtsFunction("constructor", listOf(parameter), EtsTypes.VOID, listOf(
            EtsExpressionStatement(EtsAssignment(EtsMember(self, field.name, field.type, at, field.id),
                EtsReference(parameter.symbol), at))), at, kind = EtsFunctionKind.CONSTRUCTOR)
        return listOf(EtsFile(at.file!!, listOf(EtsClass(materialImageVectorType.name,
            listOf(EtsField(field, readonly = true), constructor), at, exported = true, valueSnapshot = true))))
    }
}
