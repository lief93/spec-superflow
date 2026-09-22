@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.declarations.IrVariable
import org.jetbrains.kotlin.ir.declarations.IrValueParameter

internal class ComposeSurfaceRule(
    private val target: ArkUiCalls,
    private val content: (IrExpression, Scope) -> EtsExpression,
    private val cardContent: (IrExpression, Scope) -> EtsExpression,
    private val decorate: (IrExpression?, Scope, ComposeElement) -> List<EtsStatement>,
) : CallRule {
    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? = null
    override fun lowerUi(call: IrCall, language: Language, scope: Scope): List<EtsStatement>? {
        val api = symbolName(call.symbol.owner)
        if (api == "androidx.compose.material3.Card") return card(call, language, scope)
        if (api != "androidx.compose.material3.Surface") return null
        target.checkArguments(call, setOf("modifier", "color", "contentColor", "content"))
        val color = argument(call, "color")
        val contentColor = argument(call, "contentColor")
        val at = language.source(call)
        val context = scope.ambientValues[MATERIAL_CONTEXT]
        fun stableColor(value: EtsExpression): Boolean = when (value) {
            is EtsLiteral -> true
            is EtsReference -> value == context || scope.bindings.any { (source, binding) ->
                (binding as? EtsReference)?.symbol == value.symbol && when (val owner = source.owner) {
                    is IrVariable -> !owner.isVar
                    is IrValueParameter -> true
                    else -> false
                }
            }
            is EtsBinary -> stableColor(value.left) && stableColor(value.right)
            is EtsMember -> value.receiver.type in setOf(materialContextType, materialColorSchemeType) && stableColor(value.receiver)
            else -> false
        }
        fun colorValue(value: IrExpression): EtsExpression = language.expression(value, scope).also {
            if (!stableColor(it)) target.diagnostics.unsupported(value,
                "Surface requires a stable color value; bind effectful calls or mutable reads to a source val first")
        }
        val background = color?.let(::colorValue) ?: EtsMember(materialScheme(materialContext(scope, at), at), "surface", EtsTypes.NUMBER, at)
        val foreground = contentColor?.let(::colorValue) ?: materialContentColorFor(materialContext(scope, at), background, at)
        val body = argument(call, "content") ?: target.diagnostics.unsupported(call, "Surface requires content")
        return emit(call, language, scope, background, foreground, body, argument(call, "modifier"), false, emptyList())
    }

    private fun card(call: IrCall, language: Language, scope: Scope): List<EtsStatement> {
        val interactive = call.symbol.owner.valueParameters.any { it.name.asString() == "onClick" }
        if (interactive) target.diagnostics.unsupported(argument(call, "elevation") ?: argument(call, "onClick") ?: call,
            "Interactive Card elevation states cannot be represented by the static Harmony shadow backend")
        target.checkArguments(call, setOf("modifier", "shape", "elevation", "content"))
        val at = language.source(call)
        val context = materialContext(scope, at)
        val scheme = materialScheme(context, at)
        val background = EtsMember(scheme, "surfaceContainerHighest", EtsTypes.NUMBER, at)
        val foreground = EtsMember(scheme, "onSurface", EtsTypes.NUMBER, at)
        val shapes = language.callRules.filterIsInstance<ComposeShapeRule>().single()
        val radius = argument(call, "shape")?.let { shapes.borderRadius(it, language, scope, target.diagnostics) }
            ?: shapes.themeBorderRadius("medium", context, call, target.diagnostics)
        val elevations = language.callRules.filterIsInstance<ComposeCardElevationRule>().single()
        val elevationSource = argument(call, "elevation")
        val model = elevationSource?.let(elevations::staticElevation) ?: elevations.filledDefault(at)
        val attributes = mutableListOf(target.attribute("borderRadius", listOf(radius), call))
        if (model.default != 0.0) {
            val value = elevationSource?.let { language.expression(it, scope) } ?: elevations.targetValue(model, at)
            val converted = target.call("vp2px", listOf(elevations.defaultValue(value, at)), call,
                listOf(EtsTypes.NUMBER), EtsTypes.NUMBER)
            val shadow = target.record("ShadowOptions", linkedMapOf("radius" to converted), call)
            attributes += target.attribute("shadow", listOf(shadow), call)
        }
        val body = argument(call, "content") ?: target.diagnostics.unsupported(call, "Card requires content")
        return emit(call, language, scope, background, foreground, body, argument(call, "modifier"), true, attributes)
    }

    private fun emit(call: IrCall, language: Language, scope: Scope, background: EtsExpression,
        foreground: EtsExpression, body: IrExpression, modifier: IrExpression?, column: Boolean,
        componentAttributes: List<EtsCall>): List<EtsStatement> {
        val at = language.source(call)
        val context = scope.ambientValues[MATERIAL_CONTEXT]
        val child = scope.fork()
        if (context != null) child.ambientValues[MATERIAL_CONTEXT] = EtsNew(materialContextType,
            listOf(materialScheme(context, at), foreground, materialTypography(context, at),
                materialTextStyleOverride(context, at), materialShapes(context, at)), at)
        val slot = if (column) cardContent(body, child) else content(body, child)
        val options = target.record("__etsSurfaceOptions", linkedMapOf(
            "content" to slot, "column" to target.literal(column, call)), call)
        val element = ComposeElement(EtsUiElement(target.call("EtsComposeSurface", listOf(options), call,
            identity = "compose:surface"), attributes = listOf(
                target.attribute("backgroundColor", listOf(background), call),
                *componentAttributes.toTypedArray(),
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
                "column" to target.literal(column, call),
                "fixedWidth" to target.literal("width" in names, call),
                "fixedHeight" to target.literal("height" in names, call)), call)
            return nested.copy(call = target.call("EtsComposeSurface", listOf(boundOptions), call, identity = "compose:surface"))
        }
        val colors = target.record("SurfaceColors", linkedMapOf("fontPrimary" to foreground), call)
        val theme = target.record("SurfaceTheme", linkedMapOf("colors" to colors), call)
        val themeOptions = target.record("SurfaceThemeOptions", linkedMapOf("theme" to theme), call)
        return listOf(target.native("WithTheme", listOf(themeOptions), call,
            decorate(modifier, scope, element).map(::constrain)))
    }
}
