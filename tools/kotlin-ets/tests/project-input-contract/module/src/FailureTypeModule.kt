@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.projectinputcontract

import dev.ets.*
import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.types.IrType
import org.jetbrains.kotlin.ir.types.classOrNull

class FailureTypeModule : AdapterModule {
    override val id = "test.project-input-failures"
    override val sourceTypes = setOf("demo.projectinputs.MissingInput")
    override val projectInputs = listOf(
        AdapterProjectInput(
            AdapterCallIdentity("demo.projectinputs.wrongParameter", 0,
                parameters = listOf("kotlin.String"), returnType = "kotlin.String"),
            "kotlin.String", EtsTypes.STRING,
            kind = AdapterInputKind.TARGET_DEPENDENCY,
            parameters = listOf(AdapterTargetParameter("value", EtsTypes.NUMBER)),
            targetId = "test.wrong-parameter",
        ),
        AdapterProjectInput(
            AdapterCallIdentity("demo.projectinputs.wrongReturn", 0,
                parameters = emptyList(), returnType = "demo.projectinputs.ProjectColor"),
            "demo.projectinputs.ProjectColor", EtsTypes.STRING,
            kind = AdapterInputKind.TARGET_DEPENDENCY,
            targetId = "test.wrong-return",
        ),
        AdapterProjectInput(
            AdapterCallIdentity("demo.projectinputs.voidValue", 0,
                parameters = emptyList(), returnType = "demo.projectinputs.ProjectString"),
            "demo.projectinputs.ProjectString", EtsTypes.STRING,
            kind = AdapterInputKind.TARGET_DEPENDENCY,
            targetId = "test.void-value",
        ),
    )
    override val targetCalls = listOf(
        AdapterTargetCall("test.wrong-parameter", "wrongParameterTarget",
            EtsFunctionType(listOf(EtsTypes.NUMBER), EtsTypes.STRING)),
        AdapterTargetCall("test.wrong-return", "wrongReturnTarget",
            EtsFunctionType(emptyList(), EtsTypes.STRING)),
        AdapterTargetCall("test.void-value", "voidValueTarget",
            EtsFunctionType(emptyList(), EtsTypes.STRING)),
    )

    override fun create(target: AdapterTargetApi, ui: AdapterUiServices?): CallRule = object : CallRule {
        override fun mapType(type: IrType, language: Language): EtsType? =
            if (type.classOrNull?.owner?.let(::symbolName) in sourceTypes) EtsTypes.STRING else null

        override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? =
            if (symbolName(call.symbol.owner) == "demo.projectinputs.voidValue")
                EtsLiteral(null, EtsTypes.VOID, language.source(call)) else null
    }
}
