@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.compose

import dev.ets.*
import dev.ets.widgets.*
import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.expressions.IrExpression
import org.jetbrains.kotlin.ir.types.classOrNull

internal fun coreComposeWidgetRules(diagnostics: DiagnosticSink): List<ComposeWidgetRule> = listOf(
    ComposeMaterialThemeWidgetRule(diagnostics),
    ComposeMaterialProvideTextStyleWidgetRule(diagnostics),
    ComposeMaterialSurfaceWidgetRule(diagnostics),
    ComposeMaterialScaffoldWidgetRule(diagnostics),
    ComposeMaterialSnackbarHostWidgetRule(diagnostics),
    ComposeMaterialTopAppBarWidgetRule(diagnostics),
    ComposeMaterialIconWidgetRule(diagnostics),
)

private class ComposeMaterialThemeWidgetRule(diagnostics: DiagnosticSink) :
    ComposeMaterialWidgetRule(diagnostics), ComposeWidgetRule {
    override fun lower(call: IrCall, language: Language, scope: Scope,
        services: ComposeWidgetServices): Widget<EtsExpression, SourceSpan>? {
        if (symbolName(call.symbol.owner) != "androidx.compose.material3.MaterialTheme") return null
        checkArguments(call, setOf("colorScheme", "typography", "shapes", "content"))
        val at = language.source(call)
        val parent = materialContext(scope, at)
        val scheme = if (call.usesNativeProjectTheme == true) currentProjectColorScheme(at)
            else argument(call, "colorScheme")?.let { language.expression(it, scope) }
                ?: materialScheme(parent, at)
        val typographySource = argument(call, "typography")
        val typography = typographySource?.let { language.expression(it, scope) }
            ?: materialTypography(parent, at)
        val shapes = argument(call, "shapes")?.let { language.expression(it, scope) }
            ?: materialShapes(parent, at)
        val context = EtsReference(EtsSymbol(
            "compose-material-theme:${at.file}:${at.start}:context",
            "__etsMaterialContext${at.start}", materialContextType, at))
        val child = scope.fork()
        child.ambientValues[MATERIAL_CONTEXT] = context
        if (typographySource?.let { hasUnsupportedLineHeightStyle(it, scope) } == true)
            child.semanticFlags += LINE_HEIGHT_STYLE_CONTEXT
        val theme = newMaterialContext(at,
            MaterialContextField.COLOR_SCHEME to scheme,
            MaterialContextField.CONTENT_COLOR to materialContentColor(parent, at),
            MaterialContextField.TYPOGRAPHY to typography,
            MaterialContextField.TEXT_STYLE to EtsLiteral(null, EtsTypes.NULL, at),
            MaterialContextField.SHAPES to shapes)
        return Widget.ThemeProvider(context, theme,
            services.content(required(call, "content"), child, services.parent), at)
    }
}

private class ComposeMaterialSurfaceWidgetRule(diagnostics: DiagnosticSink) :
    ComposeMaterialWidgetRule(diagnostics), ComposeWidgetRule {
    override fun lower(call: IrCall, language: Language, scope: Scope,
        services: ComposeWidgetServices): Widget<EtsExpression, SourceSpan>? {
        if (symbolName(call.symbol.owner) != "androidx.compose.material3.Surface") return null
        checkArguments(call, setOf("modifier", "color", "contentColor", "content"))
        val at = language.source(call)
        val parent = materialContext(scope, at)
        val defaultBackground = EtsMember(materialScheme(parent, at), "surface", EtsTypes.NUMBER, at)
        fun color(name: String, fallback: EtsExpression): EtsExpression =
            argument(call, name)?.let { value ->
                resolveComposeColor(language.expression(value, scope), fallback, language.source(value))
            } ?: fallback
        val background = color("color", defaultBackground)
        val foreground = color("contentColor", materialContentColorFor(parent, background, at))
        val child = scope.fork()
        child.ambientValues[MATERIAL_CONTEXT] = newMaterialContext(at,
            MaterialContextField.COLOR_SCHEME to materialScheme(parent, at),
            MaterialContextField.CONTENT_COLOR to foreground,
            MaterialContextField.TYPOGRAPHY to materialTypography(parent, at),
            MaterialContextField.TEXT_STYLE to materialTextStyleOverride(parent, at),
            MaterialContextField.SHAPES to materialShapes(parent, at))
        val backgroundValue = WidgetValue(WidgetValueType.COLOR, background,
            WidgetValueProvenance.Expression(null), at)
        return Widget.Surface(services.content(required(call, "content"), child,
            WidgetLayoutScope.BOX), backgroundValue,
            services.modifiers(argument(call, "modifier"), scope, services.parent), at)
    }
}

private class ComposeMaterialProvideTextStyleWidgetRule(diagnostics: DiagnosticSink) :
    ComposeMaterialWidgetRule(diagnostics), ComposeWidgetRule {
    override fun lower(call: IrCall, language: Language, scope: Scope,
        services: ComposeWidgetServices): Widget<EtsExpression, SourceSpan>? {
        if (symbolName(call.symbol.owner) != "androidx.compose.material3.ProvideTextStyle") return null
        checkArguments(call, setOf("value", "content"))
        val value = required(call, "value")
        if (value.type.classOrNull?.owner?.let(::symbolName) != "androidx.compose.ui.text.TextStyle")
            diagnostics.unsupported(value, "ProvideTextStyle value requires TextStyle")
        val at = language.source(call)
        val parent = materialContext(scope, at)
        val child = scope.fork()
        child.ambientValues[MATERIAL_CONTEXT] = newMaterialContext(at,
            MaterialContextField.COLOR_SCHEME to materialScheme(parent, at),
            MaterialContextField.CONTENT_COLOR to materialContentColor(parent, at),
            MaterialContextField.TYPOGRAPHY to materialTypography(parent, at),
            MaterialContextField.TEXT_STYLE to mergeTextStyles(materialCurrentTextStyle(parent, at),
                language.expression(value, scope), at),
            MaterialContextField.SHAPES to materialShapes(parent, at))
        if (hasUnsupportedLineHeightStyle(value, scope))
            child.semanticFlags += LINE_HEIGHT_STYLE_CONTEXT
        return Widget.Group(services.content(required(call, "content"), child, services.parent), at)
    }
}

private class ComposeMaterialScaffoldWidgetRule(diagnostics: DiagnosticSink) :
    ComposeMaterialWidgetRule(diagnostics), ComposeWidgetRule {
    override fun lower(call: IrCall, language: Language, scope: Scope,
        services: ComposeWidgetServices): Widget<EtsExpression, SourceSpan>? {
        if (symbolName(call.symbol.owner) != "androidx.compose.material3.Scaffold") return null
        checkArguments(call, setOf("modifier", "topBar", "snackbarHost", "content"))
        val at = language.source(call)
        val parent = materialContext(scope, at)
        val scheme = materialScheme(parent, at)
        val child = scope.fork()
        child.ambientValues[MATERIAL_CONTEXT] = newMaterialContext(at,
            MaterialContextField.COLOR_SCHEME to scheme,
            MaterialContextField.CONTENT_COLOR to EtsMember(scheme, "onBackground", EtsTypes.NUMBER, at),
            MaterialContextField.TYPOGRAPHY to materialTypography(parent, at),
            MaterialContextField.TEXT_STYLE to materialCurrentTextStyle(parent, at),
            MaterialContextField.SHAPES to materialShapes(parent, at))
        val topBarSource = argument(call, "topBar")
        val topBar = topBarSource?.let {
            services.content(it, child, WidgetLayoutScope.BOX)
        }
        val snackbarSource = argument(call, "snackbarHost")
        val snackbar = snackbarSource?.let {
            services.content(it, child, WidgetLayoutScope.BOX)
        }
        val topInset = EtsLiteral(if (topBar == null) 0 else 64, EtsTypes.NUMBER, at)
        val zero = EtsLiteral(0, EtsTypes.NUMBER, at)
        val padding = edgePadding(listOf(zero, topInset, zero, zero), at)
        val content = services.content(required(call, "content"), child,
            WidgetLayoutScope.BOX, listOf(padding))
        val background: WidgetValue<EtsExpression, SourceSpan> = WidgetValue(WidgetValueType.COLOR,
            EtsMember(scheme, "background", EtsTypes.NUMBER, at),
            WidgetValueProvenance.ThemeToken("MaterialTheme.colorScheme.background"), at)
        return Widget.Scaffold(content, topBar, snackbar, background,
            services.modifiers(argument(call, "modifier"), scope, null), at)
    }
}

private class ComposeMaterialSnackbarHostWidgetRule(diagnostics: DiagnosticSink) :
    ComposeMaterialWidgetRule(diagnostics), ComposeWidgetRule {
    override fun lower(call: IrCall, language: Language, scope: Scope,
        services: ComposeWidgetServices): Widget<EtsExpression, SourceSpan>? {
        if (symbolName(call.symbol.owner) != "androidx.compose.material3.SnackbarHost") return null
        checkArguments(call, setOf("hostState", "modifier"))
        val stateSource = required(call, "hostState")
        val state = language.expression(stateSource, scope)
        if (state.type != snackbarHostStateType)
            diagnostics.unsupported(stateSource, "SnackbarHost requires mapped SnackbarHostState")
        return Widget.SnackbarHost(state,
            services.modifiers(argument(call, "modifier"), scope, null), language.source(call))
    }
}

private abstract class ComposeMaterialWidgetRule(protected val diagnostics: DiagnosticSink) {
    protected fun checkArguments(call: IrCall, supported: Set<String>) {
        call.symbol.owner.valueParameters.forEachIndexed { index, parameter ->
            call.getValueArgument(index)?.takeIf { parameter.name.asString() !in supported }?.let { value ->
                diagnostics.unsupported(value,
                    "Unsupported ${symbolName(call.symbol.owner)} widget argument: ${parameter.name}")
            }
        }
    }

    protected fun required(call: IrCall, name: String): IrExpression = argument(call, name)
        ?: diagnostics.unsupported(call, "${symbolName(call.symbol.owner)} requires $name")
}

private class ComposeMaterialTopAppBarWidgetRule(diagnostics: DiagnosticSink) :
    ComposeMaterialWidgetRule(diagnostics), ComposeWidgetRule {
    override fun lower(call: IrCall, language: Language, scope: Scope,
        services: ComposeWidgetServices): Widget<EtsExpression, SourceSpan>? {
        if (symbolName(call.symbol.owner) != "androidx.compose.material3.TopAppBar") return null
        checkArguments(call, setOf("title", "modifier", "navigationIcon", "actions", "expandedHeight"))
        val at = language.source(call)
        val context = materialContext(scope, at)
        val scheme = materialScheme(context, at)
        val typography = materialTypography(context, at)
        val shapes = materialShapes(context, at)
        val inheritedStyle = materialCurrentTextStyle(context, at)
        val titleStyle = EtsMember(typography, "titleLarge", textStyleType, at)
        val onSurface = EtsMember(scheme, "onSurface", EtsTypes.NUMBER, at)
        val onSurfaceVariant = EtsMember(scheme, "onSurfaceVariant", EtsTypes.NUMBER, at)

        fun content(expression: IrExpression, color: EtsExpression, style: EtsExpression,
            parent: WidgetLayoutScope): Children<EtsExpression, SourceSpan> {
            val child = scope.fork()
            child.ambientValues[MATERIAL_CONTEXT] = newMaterialContext(at,
                MaterialContextField.COLOR_SCHEME to scheme,
                MaterialContextField.CONTENT_COLOR to color,
                MaterialContextField.TYPOGRAPHY to typography,
                MaterialContextField.TEXT_STYLE to style,
                MaterialContextField.SHAPES to shapes)
            return services.content(expression, child, parent)
        }

        val height = argument(call, "expandedHeight")?.let { language.expression(it, scope) }
            ?: EtsLiteral(64, EtsTypes.NUMBER, at)
        if (height.type != EtsTypes.NUMBER)
            diagnostics.unsupported(call, "TopAppBar expandedHeight requires a Dp value")
        val title = content(required(call, "title"), onSurface, titleStyle, WidgetLayoutScope.BOX)
        val navigation = argument(call, "navigationIcon")?.let {
            content(it, onSurface, inheritedStyle, WidgetLayoutScope.ROW)
        }
        val actions = argument(call, "actions")?.let {
            content(it, onSurfaceVariant, inheritedStyle, WidgetLayoutScope.ROW)
        }
        val background: WidgetValue<EtsExpression, SourceSpan> = WidgetValue(WidgetValueType.COLOR,
            EtsMember(scheme, "surface", EtsTypes.NUMBER, at),
            WidgetValueProvenance.ThemeToken("MaterialTheme.colorScheme.surface"), at)
        return Widget.TopAppBar(title, navigation, actions, height, background,
            services.modifiers(argument(call, "modifier"), scope, null), at)
    }
}

private class ComposeMaterialIconWidgetRule(diagnostics: DiagnosticSink) :
    ComposeMaterialWidgetRule(diagnostics), ComposeWidgetRule {
    override fun lower(call: IrCall, language: Language, scope: Scope,
        services: ComposeWidgetServices): Widget<EtsExpression, SourceSpan>? {
        if (symbolName(call.symbol.owner) !in setOf(
                "androidx.compose.material.Icon", "androidx.compose.material3.Icon")) return null
        checkArguments(call, setOf("painter", "imageVector", "contentDescription", "modifier", "tint"))
        val painter = argument(call, "painter")
        val vector = argument(call, "imageVector")
        if ((painter == null) == (vector == null))
            diagnostics.unsupported(call, "Icon requires exactly one Painter or ImageVector value")
        val at = language.source(call)
        val descriptionSource = required(call, "contentDescription")
        val description = language.expression(descriptionSource, scope)
        if (description.type !in setOf(EtsTypes.STRING, EtsTypes.NULL))
            diagnostics.unsupported(descriptionSource, "Icon contentDescription requires String or null")
        val image = if (vector != null) ImageSource.Vector(language.expression(vector, scope), language.source(vector))
        else {
            val value = language.expression(painter!!, scope)
            val expected = EtsNamedType("Resource", external = true)
            if (value.type != expected)
                diagnostics.unsupported(painter, "Icon Painter requires a materialized Resource value")
            ImageSource.Resource(value, language.source(painter))
        }
        val explicit = argument(call, "tint")
        val unspecified = (explicit as? IrCall)?.symbol?.owner?.correspondingPropertySymbol?.owner
            ?.let(::symbolName) == "androidx.compose.ui.graphics.Color.Companion.Unspecified"
        val tint = when {
            unspecified -> null
            explicit != null -> services.value(explicit, scope, WidgetValueType.COLOR)
            symbolName(call.symbol.owner) == "androidx.compose.material3.Icon" -> {
                val context = materialContext(scope, at)
                WidgetValue(WidgetValueType.COLOR, materialContentColor(context, at),
                    WidgetValueProvenance.ThemeToken("LocalContentColor"), at)
            }
            else -> diagnostics.unsupported(call,
                "Material Icon default tint requires a composition content color")
        }
        if (image is ImageSource.Resource && tint != null)
            diagnostics.unsupported(call, "Tinted Painter Icon requires a target image-filter capability")
        return Widget.Image(image, description,
            services.modifiers(argument(call, "modifier"), scope, null), at, tint)
    }
}
