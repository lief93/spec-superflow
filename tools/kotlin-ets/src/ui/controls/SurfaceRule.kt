@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.declarations.IrVariable
import org.jetbrains.kotlin.ir.declarations.IrValueParameter

internal class ComposeSurfaceRule(
    private val target: ArkUiCalls,
    private val content: (IrExpression, Scope) -> EtsExpression,
    private val decorate: (IrExpression?, Scope, ComposeElement) -> List<EtsStatement>,
) : CallRule {
    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? = null
    override fun lowerUi(call: IrCall, language: Language, scope: Scope): List<EtsStatement>? {
        if (symbolName(call.symbol.owner) != "androidx.compose.material3.Surface") return null
        target.checkArguments(call, setOf("modifier", "color", "contentColor", "content"))
        val color = argument(call, "color") ?: target.diagnostics.unsupported(call,
            "Surface default background requires MaterialTheme colorScheme support")
        val contentColor = argument(call, "contentColor") ?: target.diagnostics.unsupported(call,
            "Surface default contentColor requires theme-aware contentColorFor support")
        fun stableColor(value: EtsExpression): Boolean = when (value) {
            is EtsLiteral -> true
            is EtsReference -> scope.bindings.any { (source, binding) ->
                (binding as? EtsReference)?.symbol == value.symbol && when (val owner = source.owner) {
                    is IrVariable -> !owner.isVar
                    is IrValueParameter -> true
                    else -> false
                }
            }
            is EtsBinary -> stableColor(value.left) && stableColor(value.right)
            else -> false
        }
        fun colorValue(value: IrExpression): EtsExpression = language.expression(value, scope).also {
            if (!stableColor(it)) target.diagnostics.unsupported(value,
                "Surface requires a stable color value; bind effectful calls or mutable reads to a source val first")
        }
        val background = colorValue(color)
        val foreground = colorValue(contentColor)
        val body = argument(call, "content") ?: target.diagnostics.unsupported(call, "Surface requires content")
        val slot = EtsMember(content(body, scope), "builder", EtsFunctionType(emptyList(), EtsTypes.VOID), language.source(body))
        val options = target.record("__etsSurfaceOptions", linkedMapOf("content" to slot), call)
        val element = ComposeElement(EtsUiElement(target.call("EtsComposeSurface", listOf(options), call,
            identity = "compose:surface"), attributes = listOf(
                target.attribute("backgroundColor", listOf(background), call),
                target.attribute("clip", listOf(target.literal(true, call)), call),
                target.attribute("hitTestBehavior", listOf(target.enumValue("HitTestMode", "Default", call)), call),
            )), setOf("padding", "backgroundColor"))
        fun constrain(statement: EtsStatement): EtsStatement {
            if (statement !is EtsUiElement) return statement
            val nested = statement.copy(children = statement.children?.map(::constrain))
            if ((nested.call.callee as? EtsReference)?.symbol?.id != "compose:surface") return nested
            val names = nested.attributes.map { (it.callee as? EtsReference)?.symbol?.name }
            val boundOptions = target.record("SurfaceOptions", linkedMapOf(
                "content" to slot,
                "fixedWidth" to target.literal("width" in names, call),
                "fixedHeight" to target.literal("height" in names, call)), call)
            return nested.copy(call = target.call("EtsComposeSurface", listOf(boundOptions), call, identity = "compose:surface"))
        }
        val colors = target.record("SurfaceColors", linkedMapOf("fontPrimary" to foreground), call)
        val theme = target.record("SurfaceTheme", linkedMapOf("colors" to colors), call)
        val themeOptions = target.record("SurfaceThemeOptions", linkedMapOf("theme" to theme), call)
        return listOf(target.native("WithTheme", listOf(themeOptions), call,
            decorate(argument(call, "modifier"), scope, element).map(::constrain)))
    }
}
