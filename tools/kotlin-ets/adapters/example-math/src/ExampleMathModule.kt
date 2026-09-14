@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.examples

import dev.ets.*
import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.types.*

class ExampleMathModule : AdapterModule {
    override val id = "example.math"
    override val sourceCalls = setOf("demo.adapters.absolute", "demo.adapters.record")
    override val targetCalls = listOf(
        AdapterTargetCall("example.math.abs", "abs", EtsFunctionType(listOf(EtsTypes.NUMBER), EtsTypes.NUMBER)),
        AdapterTargetCall("example.math.log", "log", EtsFunctionType(listOf(EtsTypes.STRING), EtsTypes.VOID)),
    )

    override fun create(target: AdapterTargetApi, ui: AdapterUiServices?): CallRule = object : CallRule {
        override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
            if (symbolName(call.symbol.owner) != "demo.adapters.absolute") return null
            val owner = call.symbol.owner
            if (owner.extensionReceiverParameter != null || owner.dispatchReceiverParameter != null ||
                owner.typeParameters.isNotEmpty() || owner.isSuspend ||
                owner.valueParameters.size != 1 || !owner.valueParameters.single().type.isDouble() || !owner.returnType.isDouble())
                fail(call, language, "Example absolute requires exactly one Double parameter and a Double result")
            val value = call.getValueArgument(0) ?: fail(call, language, "Example absolute requires an explicit value")
            return target.call("example.math.abs", listOf(language.expression(value, scope)), language.source(call),
                receiver("Math", language.source(call)))
        }

        override fun lowerStatement(call: IrCall, language: Language, scope: Scope): List<EtsStatement>? {
            if (symbolName(call.symbol.owner) != "demo.adapters.record") return null
            val owner = call.symbol.owner
            if (owner.extensionReceiverParameter != null || owner.dispatchReceiverParameter != null ||
                owner.typeParameters.isNotEmpty() || owner.isSuspend ||
                owner.valueParameters.size != 1 || !owner.valueParameters.single().type.isString() || !owner.returnType.isUnit())
                fail(call, language, "Example record requires exactly one String parameter and a Unit result")
            val value = call.getValueArgument(0) ?: fail(call, language, "Example record requires an explicit value")
            return listOf(EtsExpressionStatement(target.call("example.math.log", listOf(language.expression(value, scope)),
                language.source(call), receiver("console", language.source(call)))))
        }
    }

    private fun receiver(name: String, source: SourceSpan) =
        EtsReference(EtsSymbol("example.math.receiver:$name", name, EtsTypes.OBJECT, source, external = true))

    private fun fail(call: IrCall, language: Language, message: String): Nothing =
        throw Unsupported(Diagnostic("UNSUPPORTED", message, language.source(call)))
}
