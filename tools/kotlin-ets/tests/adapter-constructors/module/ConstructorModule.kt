@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package constructoradapter

import dev.ets.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.*

class ConstructorModule : AdapterModule {
    override val id = "test.constructors"
    override val sourceTypes = setOf("constructorapi.Amount", "constructorapi.Wrong",
        "constructorapi.Effect", "constructorapi.Unclaimed", "constructorapi.Token", "constructorapi.WrongObject", "constructorapi.EffectObject")
    override val sourceCalls = setOf("constructorapi.Amount.<init>", "constructorapi.Amount.<get-value>",
        "constructorapi.Wrong.<init>", "constructorapi.Effect.<init>", "constructorapi.Token.<get-value>",
        "constructorapi.goodEffect", "constructorapi.badEffect", "constructorapi.wrongValue",
        "constructorapi.adaptedMagnitude", "constructorapi.adaptedEffect", "constructorvalues.sourceBody")
    override val targetCalls = listOf(
        AdapterTargetCall("test.dependencies.magnitude", "abs", EtsFunctionType(listOf(EtsTypes.NUMBER), EtsTypes.NUMBER)),
        AdapterTargetCall("test.dependencies.effect", "log", EtsFunctionType(listOf(EtsTypes.STRING), EtsTypes.VOID)),
    )
    override fun create(target: AdapterTargetApi, ui: AdapterUiServices?): CallRule = object : CallRule {
        override fun mapType(type: IrType, language: Language): EtsType? =
            if (type.classOrNull?.owner?.let(::symbolName) in sourceTypes) EtsTypes.NUMBER else null

        override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? =
            when (symbolName(call.symbol.owner)) {
                "constructorapi.Amount.<get-value>", "constructorapi.Token.<get-value>" ->
                    language.expression(call.dispatchReceiver!!, scope)
                "constructorapi.badEffect" -> EtsCall(EtsLambda(emptyList(), emptyList(), EtsTypes.VOID,
                    language.source(call)), emptyList(), EtsTypes.VOID, language.source(call))
                "constructorapi.wrongValue" -> EtsLiteral("wrong", EtsTypes.STRING, language.source(call))
                "constructorapi.adaptedMagnitude" -> target.call("test.dependencies.magnitude",
                    listOf(language.expression(argument(call, "value")!!, scope)), language.source(call),
                    receiver("Math", language.source(call)))
                "constructorvalues.sourceBody" -> EtsLiteral(99, EtsTypes.NUMBER, language.source(call))
                else -> null
            }

        override fun lowerStatement(call: IrCall, language: Language, scope: Scope): List<EtsStatement>? =
            when (symbolName(call.symbol.owner)) {
                "constructorapi.goodEffect" ->
                    listOf(EtsExpressionStatement(EtsLiteral(31, EtsTypes.NUMBER, language.source(call))))
                "constructorapi.adaptedEffect" -> listOf(EtsExpressionStatement(target.call("test.dependencies.effect",
                    listOf(language.expression(argument(call, "value")!!, scope)), language.source(call),
                    receiver("console", language.source(call)))))
                else -> null
            }

        override fun lowerObject(value: IrGetObjectValue, language: Language, scope: Scope): EtsExpression? =
            when (symbolName(value.symbol.owner)) {
                "constructorapi.Token" -> EtsLiteral(9, EtsTypes.NUMBER, language.source(value))
                "constructorapi.WrongObject" -> EtsLiteral("wrong", EtsTypes.STRING, language.source(value))
                "constructorapi.EffectObject" -> EtsUndefined(language.source(value))
                else -> null
            }

        override fun lowerConstructor(call: IrConstructorCall, language: Language, scope: Scope): EtsExpression? =
            when (symbolName(call.symbol.owner)) {
                "constructorapi.Amount.<init>" -> language.expression(argument(call, "value")!!, scope)
                "constructorapi.Wrong.<init>" -> EtsLiteral("wrong", EtsTypes.STRING, language.source(call))
                "constructorapi.Effect.<init>" -> EtsCall(EtsLambda(emptyList(), emptyList(), EtsTypes.VOID,
                    language.source(call)), emptyList(), EtsTypes.VOID, language.source(call))
                else -> null
            }

        private fun receiver(name: String, source: SourceSpan) =
            EtsReference(EtsSymbol("test.dependencies.receiver:$name", name, EtsTypes.OBJECT, source, external = true))
    }
}
