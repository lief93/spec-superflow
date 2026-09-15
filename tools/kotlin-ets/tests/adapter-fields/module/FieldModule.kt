@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package fieldadapter
import dev.ets.*
import org.jetbrains.kotlin.ir.expressions.*

class FieldModule : AdapterModule {
    override val id = "test.fields"
    override val sourceCalls = emptySet<String>()
    override val sourceFields = setOf("fieldapi.Api.value", "fieldapi.Api.wrong", "fieldapi.Api.effect")
    override fun create(target: AdapterTargetApi, ui: AdapterUiServices?): CallRule = object : CallRule {
        override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? = null
        override fun lowerField(value: IrGetField, language: Language, scope: Scope): EtsExpression? =
            when (symbolName(value.symbol.owner)) {
                "fieldapi.Api.value" -> EtsLiteral(7, EtsTypes.NUMBER, language.source(value))
                "fieldapi.Api.wrong" -> EtsLiteral("wrong", EtsTypes.STRING, language.source(value))
                "fieldapi.Api.effect" -> EtsCall(EtsLambda(emptyList(), emptyList(), EtsTypes.VOID,
                    language.source(value)), emptyList(), EtsTypes.VOID, language.source(value))
                else -> null
            }
    }
}
