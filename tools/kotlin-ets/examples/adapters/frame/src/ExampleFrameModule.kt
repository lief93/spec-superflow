@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.examples

import dev.ets.*
import dev.ets.compose.*
import dev.ets.widgets.*
import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.types.isString
import org.jetbrains.kotlin.ir.types.isUnit

class ExampleFrameModule : AdapterModule, ComposeWidgetAdapterModule {
    override val id = "example.frame"
    override val sourceCalls = setOf("demo.adapters.Frame")
    override fun create(target: AdapterTargetApi, ui: AdapterUiServices?): CallRule = object : CallRule {
        override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? = null
    }

    override fun createWidgetRule(): ComposeWidgetRule = ComposeWidgetRule { call, language, scope, services ->
            if (symbolName(call.symbol.owner) != "demo.adapters.Frame") return@ComposeWidgetRule null
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
            val title = Widget.Text(services.value(label, scope, WidgetValueType.STRING),
                WidgetTextStyle(null, null, null, null), emptyList(), source)
            val children = services.content(content, scope, WidgetLayoutScope.COLUMN)
            Widget.Column(Children(listOf(title) + children.widgets),
                services.modifiers(modifier, scope, null), source)
        }

    private fun fail(call: IrCall, language: Language, message: String): Nothing =
        throw Unsupported(Diagnostic("UNSUPPORTED", message, language.source(call)))
}
