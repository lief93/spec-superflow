@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.expressions.*

internal const val LAYOUT_AXIS = "compose:layoutAxis"
internal fun isWeightModifier(call: IrCall) = symbolName(call.symbol.owner) in setOf(
    "androidx.compose.foundation.layout.RowScope.weight", "androidx.compose.foundation.layout.ColumnScope.weight")
private val weightSource = SourceSpan("EtsLayoutWeight.kt", 0, 0)
private val weightFunction = layoutWeightFunction()

internal fun layoutWeight(value: EtsExpression, at: SourceSpan): EtsExpression {
    val constant = (value as? EtsLiteral)?.value as? Number
    if (constant != null) {
        if (!(constant.toDouble() > 0)) throw Unsupported(Diagnostic("UNSUPPORTED", "weight must be positive", at))
        return EtsLiteral(minOf(constant.toDouble(), Float.MAX_VALUE.toDouble()), EtsTypes.NUMBER, at)
    }
    return EtsCall(EtsReference(weightFunction.symbol, at), listOf(value), EtsTypes.NUMBER, at)
}

internal class ComposeWeightRule : CallRule {
    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? = null
    override fun targetFiles(program: EtsProgram): List<EtsFile> {
        var used = false
        program.files.forEach { file -> file.declarations.forEach { declaration -> walkEts(declaration) { node ->
            if (node is EtsReference && node.symbol.id == weightFunction.symbol.id) used = true
        } } }
        return if (used) listOf(EtsFile(weightSource.file!!, listOf(weightFunction))) else emptyList()
    }
}

private fun layoutWeightFunction(): EtsFunction {
    val at = weightSource
    val parameter = EtsParameter(EtsSymbol("layoutWeight:weight", "weight", EtsTypes.NUMBER, at))
    val value = EtsReference(parameter.symbol)
    val fail = EtsCall(EtsReference(EtsSymbol("stdlib:__etsIllegalArgumentException", "__etsIllegalArgumentException",
        EtsFunctionType(listOf(EtsTypes.STRING), EtsTypes.NEVER), at, true)),
        listOf(EtsLiteral("invalid weight; must be greater than zero", EtsTypes.STRING, at)), EtsTypes.NEVER, at)
    val max = EtsLiteral(Float.MAX_VALUE.toDouble(), EtsTypes.NUMBER, at)
    return EtsFunction("__etsLayoutWeight", listOf(parameter), EtsTypes.NUMBER, listOf(
        EtsIf(listOf(EtsBranch(EtsUnary("!", EtsBinary(">", value, EtsLiteral(0, EtsTypes.NUMBER, at), EtsTypes.BOOLEAN, at),
            EtsTypes.BOOLEAN, at), listOf(EtsExpressionStatement(fail)))), at),
        EtsReturn(EtsConditional(EtsBinary(">", value, max, EtsTypes.BOOLEAN, at), max, value, EtsTypes.NUMBER, at), at)), at, exported = true)
}
