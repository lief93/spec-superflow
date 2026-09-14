@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.isString

internal data class ComposeElement(val element: EtsUiElement,
    val modifierBoundaries: Set<String> = emptySet(), val touch: TouchTargets? = null)

internal abstract class ComposeControlRule(
    private val decorate: (IrExpression?, Scope, ComposeElement) -> List<EtsStatement>,
) : CallRule {
    final override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? = null
    final override fun lowerUi(call: IrCall, language: Language, scope: Scope): List<EtsStatement>? {
        val element = control(call, language, scope) ?: return null
        return decorate(argument(call, "modifier"), scope, element)
    }
    protected abstract fun control(call: IrCall, language: Language, scope: Scope): ComposeElement?
}

internal class ComposeLayoutRule(
    private val target: ArkUiCalls,
    private val content: (IrExpression, Scope) -> List<EtsStatement>,
    private val touchBoxes: MutableMap<IrCall, TouchTargets>,
    decorate: (IrExpression?, Scope, ComposeElement) -> List<EtsStatement>,
) : ComposeControlRule(decorate) {
    override fun control(call: IrCall, language: Language, scope: Scope): ComposeElement? {
        val component = when (symbolName(call.symbol.owner)) {
            "androidx.compose.foundation.layout.Column" -> "Column"
            "androidx.compose.foundation.layout.Row" -> "Row"
            "androidx.compose.foundation.layout.Box" -> "Stack"
            "androidx.compose.foundation.layout.Spacer" -> {
                target.checkArguments(call, setOf("modifier"))
                return ComposeElement(target.native("Row", emptyList(), call, emptyList()))
            }
            else -> return null
        }
        target.checkArguments(call, setOf("modifier", "content"))
        val touch = if (component == "Row") touchTargets(call, scope, target.diagnostics) else null
        if (touch != null) touchBoxes[touch.box] = touch
        val children = argument(call, "content")?.let { content(it, scope) } ?: emptyList()
        val attrs = mutableListOf<EtsCall>()
        if (component == "Column") attrs += target.attribute("alignItems", listOf(target.enumValue("HorizontalAlign", "Start", call)), call)
        if (component == "Row") attrs += target.attribute("alignItems", listOf(target.enumValue("VerticalAlign", "Top", call)), call)
        if (touch != null) {
            val source = language.source(call)
            attrs += target.attribute("responseRegion", listOf(touch.rowRegion(source)), call)
            val items = EtsSymbol("ui:touch:${call.startOffset}", "items", EtsNamedType("Array", listOf(EtsNamedType("TouchTestInfo"))), source)
            val dispatch = target.call("__etsNearestTouch", listOf(EtsReference(items), target.literal(touch.inset, call),
                target.literal(touch.width, call), target.literal(touch.height, call)), call,
                result = EtsNamedType("TouchResult"), identity = "compose:nearestTouch")
            attrs += target.attribute("onChildTouchTest", listOf(EtsLambda(listOf(EtsParameter(items)),
                listOf(EtsReturn(dispatch, source)), dispatch.type, source)), call)
        }
        return ComposeElement(target.native(component, if (component == "Stack") listOf(target.stackOptions(call)) else emptyList(),
            call, children).copy(attributes = attrs), touch = touchBoxes[call])
    }
}

internal class ComposeTextRule(
    private val target: ArkUiCalls,
    private val color: (IrExpression, Scope) -> EtsExpression,
    private val dimension: (IrExpression, Scope, String) -> EtsExpression,
    private val typography: () -> MaterialTextContext,
    decorate: (IrExpression?, Scope, ComposeElement) -> List<EtsStatement>,
) : ComposeControlRule(decorate) {
    override fun control(call: IrCall, language: Language, scope: Scope): ComposeElement? {
        val api = symbolName(call.symbol.owner)
        if (api !in setOf("androidx.compose.material3.Text", "androidx.compose.material.Text")) return null
        target.checkArguments(call, setOf("text", "modifier", "color", "fontSize"))
        val text = argument(call, "text") ?: target.diagnostics.unsupported(call, "Text requires text")
        if (!text.type.isString()) target.diagnostics.unsupported(text, "AnnotatedString Text is not supported")
        val attrs = buildList {
            argument(call, "color")?.let { add(target.attribute("fontColor", listOf(color(it, scope)), call)) }
            val size = argument(call, "fontSize")?.let { dimension(it, scope, "sp") }
            if (api == "androidx.compose.material3.Text") {
                val context = typography()
                add(target.attribute("attributeModifier", listOf(EtsNew(
                    EtsNamedType("__etsMaterialTypography", symbolId = "compose:materialTypography", external = true),
                    listOf(size ?: target.literal(context.size, call), target.literal(context.lineHeight, call),
                        target.literal(context.weight, call), target.literal(context.tracking, call)), language.source(call))), call))
            } else if (size != null) add(target.attribute("fontSize", listOf(size), call))
        }
        return ComposeElement(target.native("Text", listOf(language.expression(text, scope)), call).copy(attributes = attrs),
            if (api == "androidx.compose.material3.Text") setOf("padding") else emptySet())
    }
}

internal class ComposeButtonRule(
    private val target: ArkUiCalls,
    private val content: (IrExpression, Scope) -> List<EtsStatement>,
    private val callback: (IrExpression, Scope) -> EtsExpression,
    decorate: (IrExpression?, Scope, ComposeElement) -> List<EtsStatement>,
) : ComposeControlRule(decorate) {
    override fun control(call: IrCall, language: Language, scope: Scope): ComposeElement? {
        if (symbolName(call.symbol.owner) !in setOf("androidx.compose.material3.Button", "androidx.compose.material.Button")) return null
        target.checkArguments(call, setOf("onClick", "modifier", "enabled", "content"))
        val body = argument(call, "content") ?: target.diagnostics.unsupported(call, "Button requires content")
        val click = argument(call, "onClick") ?: target.diagnostics.unsupported(call, "Button requires callback")
        val row = target.native("Row", emptyList(), call, content(body, scope)).copy(attributes = listOf(
            target.attribute("alignItems", listOf(target.enumValue("VerticalAlign", "Center", call)), call),
            target.attribute("justifyContent", listOf(target.enumValue("FlexAlign", "Center", call)), call)))
        val attrs = listOf(target.attribute("onClick", listOf(callback(click, scope)), call)) + listOfNotNull(
            argument(call, "enabled")?.let { target.attribute("enabled", listOf(language.expression(it, scope)), call) })
        return ComposeElement(target.native("Button", emptyList(), call, listOf(row)).copy(attributes = attrs),
            setOf("padding", "backgroundColor", "onClick", "enabled"))
    }
}
