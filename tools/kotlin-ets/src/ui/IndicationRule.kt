@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.types.IrType
import org.jetbrains.kotlin.ir.types.classOrNull

private val indicationSource = SourceSpan("EtsIndication.kt", -1, -1)
private val indicationType = etsClassSymbol("EtsIndication", indicationSource).type as EtsNamedType

internal class ComposeIndicationRule(private val diagnostics: DiagnosticSink) : CallRule {
    override fun mapType(type: IrType, language: Language): EtsType? {
        val owner = type.classOrNull?.owner ?: return null
        if (sourceFile(owner) != null) return null
        return when (symbolName(owner)) {
            "androidx.compose.foundation.Indication",
            "androidx.compose.foundation.IndicationNodeFactory" -> indicationType
            else -> null
        }
    }

    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        if (sourceFile(call.symbol.owner) != null ||
            symbolName(call.symbol.owner) !in setOf("androidx.compose.material.ripple.rememberRipple",
                "androidx.compose.material3.ripple")) return null
        diagnostics.omitUi(call, "Compose press indication is omitted from the static interaction projection",
            symbolName(call.symbol.owner), "omitted_animation_modifier",
            "Click action and enabled state are preserved; ripple rendering and animation are omitted.",
            (0 until call.valueArgumentsCount).mapNotNull(call::getValueArgument))
        return EtsNew(indicationType, emptyList(), language.source(call))
    }

    override fun targetFiles(program: EtsProgram): List<EtsFile> {
        var used = false
        program.files.forEach { file -> file.declarations.forEach { declaration ->
            walkEts(declaration) { node ->
                if (node is EtsExpression && node.type == indicationType) used = true
            }
        } }
        if (!used) return emptyList()
        val constructor = EtsFunction("constructor", emptyList(), EtsTypes.VOID, emptyList(), indicationSource,
            kind = EtsFunctionKind.CONSTRUCTOR)
        return listOf(EtsFile(indicationSource.file!!,
            listOf(EtsClass(indicationType.name, listOf(constructor), indicationSource, exported = true))))
    }
}
