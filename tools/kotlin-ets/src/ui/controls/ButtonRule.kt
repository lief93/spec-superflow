@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.declarations.*

internal class ComposeButtonRule(
    private val target: ArkUiCalls,
    private val content: (IrExpression, Scope) -> List<EtsStatement>,
    private val callback: (IrExpression, Scope) -> EtsExpression,
    private val decorate: (IrExpression?, Scope, ComposeElement) -> List<EtsStatement>,
) : CallRule {
    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? = null
    override fun lowerUi(call: IrCall, language: Language, scope: Scope): List<EtsStatement>? {
        val element = control(call, language, scope) ?: return null
        val decorated = decorate(argument(call, "modifier"), scope, element)
        if (symbolName(call.symbol.owner) == "androidx.compose.material.Button") return decorated
        val enabled = argument(call, "enabled")?.let { language.expression(it, scope) } ?: target.literal(true, call)
        val root = decorated.singleOrNull() as? EtsUiElement
        val parentData = root?.attributes?.filter { (it.callee as? EtsReference)?.symbol?.name == "layoutWeight" }.orEmpty()
        val children = if (root != null) listOf(root.copy(attributes = root.attributes - parentData.toSet())) else decorated
        // Native Button multiplies disabled opacity. Gate input on a plain parent
        // so explicit source disabled colors are not dimmed a second time.
        return listOf(target.native("Stack", listOf(target.stackOptions(call)), call, children).copy(attributes = parentData +
            target.attribute("enabled", listOf(enabled), call)))
    }
    private fun control(call: IrCall, language: Language, scope: Scope): ComposeElement? {
        val api = symbolName(call.symbol.owner)
        if (api !in setOf("androidx.compose.material3.Button", "androidx.compose.material3.TextButton", "androidx.compose.material.Button")) return null
        if (api != "androidx.compose.material.Button") return materialButton(call, language, scope, api.endsWith("TextButton"))
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

    private fun materialButton(call: IrCall, language: Language, scope: Scope, text: Boolean): ComposeElement {
        target.checkArguments(call, setOf("onClick", "modifier", "enabled", "content", "colors", "shape", "contentPadding"))
        val at = language.source(call)
        val context = materialContext(scope, at)
        val enabled = argument(call, "enabled")?.let { language.expression(it, scope) } ?: target.literal(true, call)
        val palette = argument(call, "colors")?.let { language.expression(it, scope) } ?: defaultButtonColors(scope, at, text)
        fun repeatable(value: EtsExpression): Boolean = when (value) {
            is EtsLiteral -> true
            is EtsReference -> value == context || scope.bindings.any { (symbol, binding) -> binding == value && when (val owner = symbol.owner) {
                is IrVariable -> !owner.isVar
                is IrValueParameter -> true
                else -> false
            } }
            is EtsMember -> value.receiver.type in setOf(buttonColorsType, materialContextType, materialColorSchemeType) && repeatable(value.receiver)
            is EtsNew -> value.classType in setOf(buttonColorsType, materialContextType, materialColorSchemeType) && value.arguments.all(::repeatable)
            is EtsBinary -> repeatable(value.left) && repeatable(value.right)
            is EtsConditional -> repeatable(value.condition) && repeatable(value.whenTrue) && repeatable(value.whenFalse)
            else -> false
        }
        if (!repeatable(enabled) || !repeatable(palette)) target.diagnostics.unsupported(call,
            "Button colors/enabled require stable values; bind effectful expressions to source vals")
        fun selected(name: String): EtsExpression = EtsConditional(enabled,
            EtsMember(palette, name, EtsTypes.NUMBER, at),
            EtsMember(palette, "disabled" + name.replaceFirstChar { it.uppercaseChar() }, EtsTypes.NUMBER, at), EtsTypes.NUMBER, at)
        val child = scope.fork()
        child.ambientValues[MATERIAL_CONTEXT] = EtsNew(materialContextType, listOf(materialScheme(context, at), selected("contentColor")), at)
        val body = argument(call, "content") ?: target.diagnostics.unsupported(call, "Button requires content")
        val click = argument(call, "onClick") ?: target.diagnostics.unsupported(call, "Button requires callback")
        val padding = argument(call, "contentPadding")?.let { language.expression(it, scope) }
            ?: symmetricPadding(target.literal(if (text) 12 else 24, call), target.literal(8, call), at)
        val shape = argument(call, "shape")?.let { language.expression(it, scope) } ?: target.literal("50%", call)
        val row = target.native("Row", emptyList(), call, content(body, child)).copy(attributes = listOf(
            target.attribute("alignItems", listOf(target.enumValue("VerticalAlign", "Center", call)), call),
            target.attribute("justifyContent", listOf(target.enumValue("FlexAlign", "Center", call)), call)))
        val clickValue = callback(click, scope)
        if (clickValue !is EtsReference && clickValue !is EtsLambda) target.diagnostics.unsupported(click,
            "Button callback factory requires a source val to preserve registration-time evaluation")
        val guardedClick = EtsLambda(emptyList(), listOf(EtsIf(listOf(EtsBranch(enabled,
            listOf(EtsExpressionStatement(EtsCall(clickValue, emptyList(), EtsTypes.VOID, at))))), at)), EtsTypes.VOID, at)
        val attrs = listOf(
            target.attribute("type", listOf(target.enumValue("ButtonType", "Normal", call)), call),
            target.attribute("onClick", listOf(guardedClick), call),
            target.attribute("focusable", listOf(enabled), call),
            target.attribute("backgroundColor", listOf(selected("containerColor")), call),
            target.attribute("borderRadius", listOf(shape), call),
            target.attribute("padding", listOf(padding), call),
            target.attribute("height", listOf(target.literal("auto", call)), call),
            target.attribute("constraintSize", listOf(target.record("ConstraintSizeOptions", linkedMapOf(
                "minWidth" to target.literal(58, call), "minHeight" to target.literal(40, call)), call)), call))
        return ComposeElement(target.native("Button", emptyList(), call, listOf(row)).copy(attributes = attrs),
            setOf("padding", "backgroundColor", "onClick", "enabled"), orderedArguments = listOf(padding, shape))
    }
}
