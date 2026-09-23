@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.*

private val emptyModifierSource = SourceSpan("EtsEmptyModifier.kt", 0, 0)
internal val emptyModifierType = etsClassSymbol("EtsEmptyModifier", emptyModifierSource).type as EtsNamedType
private val emptyModifier = EtsSymbol("compose:emptyModifier", "__etsEmptyModifier", emptyModifierType, emptyModifierSource)
internal fun emptyModifierValue(at: SourceSpan) = EtsReference(emptyModifier, at)

/** Only the identity value is representable here; modifier chains are not erased to it. */
internal class ComposeEmptyModifierRule : CallRule {
    override fun mapType(type: IrType, language: Language): EtsType? {
        val owner = type.classOrNull?.owner ?: return null
        return if (sourceFile(owner) == null && symbolName(owner) in setOf("androidx.compose.ui.Modifier", "androidx.compose.ui.Modifier.Companion"))
            emptyModifierType else null
    }
    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? = null
    override fun lowerObject(value: IrGetObjectValue, language: Language, scope: Scope): EtsExpression? =
        if (sourceFile(value.symbol.owner) == null && symbolName(value.symbol.owner) == "androidx.compose.ui.Modifier.Companion")
            emptyModifierValue(language.source(value)) else null

    override fun targetFiles(program: EtsProgram): List<EtsFile> {
        fun uses(type: EtsType): Boolean = when (type) {
            is EtsNamedType -> type.symbolId == emptyModifierType.symbolId || type.arguments.any(::uses)
            is EtsFunctionType -> type.parameters.any(::uses) || uses(type.result)
            is EtsNullableType -> uses(type.inner)
            else -> false
        }
        var used = false
        program.files.forEach { file -> file.declarations.forEach { declaration -> walkEts(declaration) { node ->
            if (node is EtsExpression && uses(node.type) || node is EtsFunction && uses(node.symbol.type)) used = true
        } } }
        if (!used) return emptyList()
        return listOf(EtsFile(emptyModifierSource.file!!, listOf(
            EtsClass(emptyModifierType.name, listOf(EtsFunction("constructor", emptyList(), EtsTypes.VOID,
                emptyList(), emptyModifierSource, kind = EtsFunctionKind.CONSTRUCTOR)), emptyModifierSource, exported = true),
            EtsGlobal(emptyModifier, EtsNew(emptyModifierType, emptyList(), emptyModifierSource), false, exported = true))))
    }
}
