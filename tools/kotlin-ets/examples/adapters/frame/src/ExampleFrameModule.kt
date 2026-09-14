@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.examples

import dev.ets.*
import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.types.isString
import org.jetbrains.kotlin.ir.types.isUnit

class ExampleFrameModule : AdapterModule {
    override val id = "example.frame"
    override val sourceCalls = setOf("demo.adapters.Frame")
    override val targetCalls = listOf(
        AdapterTargetCall("example.frame.column", "Column", EtsFunctionType(emptyList(), EtsTypes.VOID)),
        AdapterTargetCall("example.frame.text", "Text", EtsFunctionType(listOf(EtsTypes.STRING), EtsTypes.VOID)),
    )

    override fun create(target: AdapterTargetApi, ui: AdapterUiServices?): CallRule = object : CallRule {
        override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? = null

        override fun lowerUi(call: IrCall, language: Language, scope: Scope): List<EtsStatement>? {
            if (ui == null || symbolName(call.symbol.owner) != "demo.adapters.Frame") return null
            val owner = call.symbol.owner
            if (owner.extensionReceiverParameter != null || owner.dispatchReceiverParameter != null ||
                owner.typeParameters.isNotEmpty() || owner.isSuspend ||
                owner.valueParameters.any { it.varargElementType != null } ||
                owner.valueParameters.map { it.name.asString() } != listOf("label", "modifier", "content") ||
                !owner.valueParameters.first().type.isString() || !owner.returnType.isUnit())
                fail(call, language, "Example Frame requires label, modifier and content parameters")
            val label = argument(call, "label") ?: fail(call, language, "Example Frame requires a label")
            val modifier = argument(call, "modifier") ?: fail(call, language,
                "Example Frame requires an explicit modifier; omitted defaults are unsupported")
            val content = argument(call, "content") ?: fail(call, language, "Example Frame requires content")
            val source = language.source(call)
            val title = EtsUiElement(target.call("example.frame.text", listOf(language.expression(label, scope)), source))
            val column = EtsUiElement(target.call("example.frame.column", emptyList(), source),
                listOf(title) + ui.content(content, scope))
            return ui.decorate(modifier, scope, column)
        }
    }

    private fun fail(call: IrCall, language: Language, message: String): Nothing =
        throw Unsupported(Diagnostic("UNSUPPORTED", message, language.source(call)))
}
