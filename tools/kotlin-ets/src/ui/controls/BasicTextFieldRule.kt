@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.declarations.IrFunction
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.isString

internal class ComposeBasicTextFieldRule(
    private val target: ArkUiCalls,
    private val bindInnerField: (org.jetbrains.kotlin.ir.symbols.IrValueSymbol, EtsUiElement, Scope, SourceSpan) -> Unit,
    private val body: (IrFunction, Scope) -> List<EtsStatement>,
    decorate: (IrExpression?, Scope, ComposeElement) -> List<EtsStatement>,
) : ComposeControlRule(decorate) {
    override fun control(call: IrCall, language: Language, scope: Scope): ComposeElement? {
        if (symbolName(call.symbol.owner) != "androidx.compose.foundation.text.BasicTextField") return null
        target.checkArguments(call, setOf("value", "onValueChange", "modifier", "enabled", "readOnly",
            "textStyle", "keyboardOptions", "keyboardActions", "singleLine", "maxLines",
            "visualTransformation", "interactionSource", "decorationBox"))
        val value = argument(call, "value") ?: target.diagnostics.unsupported(call, "BasicTextField requires value")
        if (!value.type.isString()) target.diagnostics.unsupported(value, "BasicTextField requires a String value")
        val change = argument(call, "onValueChange")
            ?: target.diagnostics.unsupported(call, "BasicTextField requires onValueChange")
        val at = language.source(call)
        val text = language.expression(value, scope)
        val options = target.record("TextInputOptions", linkedMapOf("text" to text), call)
        val password = argument(call, "visualTransformation")?.let { language.expression(it, scope) }
            ?.let(::isPasswordTransformation)
        val inputType = password?.let {
            EtsConditional(it, target.enumValue("InputType", "Password", call),
                target.enumValue("InputType", "Normal", call), EtsNamedType("InputType"), at)
        } ?: target.enumValue("InputType", "Normal", call)
        val attrs = buildList {
            add(target.attribute("type", listOf(inputType), call))
            add(target.attribute("onChange", listOf(language.expression(change, scope)), call))
            argument(call, "enabled")?.let { add(target.attribute("enabled", listOf(language.expression(it, scope)), call)) }
            argument(call, "maxLines")?.let { add(target.attribute("maxLines", listOf(language.expression(it, scope)), call)) }
            listOf("readOnly", "singleLine", "textStyle", "keyboardOptions", "keyboardActions",
                "interactionSource").forEach { name ->
                argument(call, name)?.let { language.expression(it, scope) }
            }
        }
        val field = target.native("TextInput", listOf(options), call).copy(attributes = attrs)
        val decoration = argument(call, "decorationBox") ?: return ComposeElement(field,
            setOf("padding", "backgroundColor", "onClick", "enabled"))
        val fn = lambda(decoration, scope)
            ?: target.diagnostics.unsupported(decoration, "BasicTextField decorationBox requires a source lambda")
        val inner = fn.valueParameters.singleOrNull()
            ?: target.diagnostics.unsupported(fn, "BasicTextField decorationBox requires the innerTextField slot")
        val child = scope.fork()
        bindInnerField(inner.symbol, field, child, language.source(fn))
        val decorated = body(fn, child)
        val root = decorated.singleOrNull() as? EtsUiElement
            ?: return ComposeElement(target.native("Stack", listOf(target.stackOptions(call)), call, decorated),
                setOf("padding", "backgroundColor", "onClick", "enabled"))
        return ComposeElement(root, setOf("padding", "backgroundColor", "onClick", "enabled"))
    }
}
