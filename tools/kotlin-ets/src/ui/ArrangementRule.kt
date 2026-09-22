@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.types.IrType
import org.jetbrains.kotlin.ir.types.classOrNull

private val arrangementSource = SourceSpan("EtsArrangement.kt", 0, 0)
private val arrangementType = etsClassSymbol("EtsArrangement", arrangementSource).type as EtsNamedType
private val arrangementSpace = EtsSymbol("arrangement:space", "space", EtsTypes.NUMBER, arrangementSource)

/** Fixed spacing remains a value across source helpers, parameters and UI calls. */
internal class ComposeArrangementRule : CallRule {
    override fun mapType(type: IrType, language: Language): EtsType? {
        val owner = type.classOrNull?.owner ?: return null
        return if (sourceFile(owner) == null && symbolName(owner) in setOf(
            "androidx.compose.foundation.layout.Arrangement.Horizontal",
            "androidx.compose.foundation.layout.Arrangement.Vertical",
            "androidx.compose.foundation.layout.Arrangement.HorizontalOrVertical")) arrangementType else null
    }

    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        val owner = call.symbol.owner
        if (sourceFile(owner) != null || symbolName(owner) != "androidx.compose.foundation.layout.Arrangement.spacedBy") return null
        if (owner.valueParameters.map { it.name.asString() } != listOf("space"))
            throw Unsupported(Diagnostic("UNSUPPORTED", "Arrangement.spacedBy alignment overload is not supported", language.source(call)))
        val space = argument(call, "space") ?: return null
        return EtsNew(arrangementType, listOf(requireSpecifiedDp(language.expression(space, scope),
            language.source(space), "Arrangement.spacedBy")), language.source(call))
    }

    override fun targetFiles(program: EtsProgram): List<EtsFile> {
        var used = false
        program.files.forEach { it.declarations.forEach { declaration -> walkEts(declaration) {
            if (it is EtsNew && it.type == arrangementType) used = true
        } } }
        if (!used) return emptyList()
        val at = arrangementSource
        val parameter = EtsParameter(EtsSymbol("arrangement:initial", "space", EtsTypes.NUMBER, at))
        val self = EtsReference(EtsSymbol("arrangement:this", "this", arrangementType, at, external = true))
        val constructor = EtsFunction("constructor", listOf(parameter), EtsTypes.VOID, listOf(EtsExpressionStatement(
            EtsAssignment(EtsMember(self, "space", EtsTypes.NUMBER, at, arrangementSpace.id), EtsReference(parameter.symbol), at))),
            at, kind = EtsFunctionKind.CONSTRUCTOR)
        return listOf(EtsFile(at.file!!, listOf(EtsClass(arrangementType.name,
            listOf(EtsField(arrangementSpace, readonly = true), constructor), at, exported = true))))
    }
}

internal fun arrangementOptions(value: EtsExpression, control: String, target: ArkUiCalls, call: IrCall): EtsExpression {
    if (value.type != arrangementType) target.diagnostics.unsupported(call, "Expected a supported fixed-spacing Arrangement")
    return target.record("${control}Options", linkedMapOf("space" to
        EtsMember(value, "space", EtsTypes.NUMBER, value.source, arrangementSpace.id)), call)
}
