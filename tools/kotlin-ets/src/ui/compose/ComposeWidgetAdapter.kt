@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.compose

import dev.ets.*
import dev.ets.widgets.*
import java.net.URI
import org.jetbrains.kotlin.descriptors.ClassKind
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.IrStatement
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.symbols.IrValueSymbol
import org.jetbrains.kotlin.ir.types.*
import org.jetbrains.kotlin.ir.util.*
import org.jetbrains.kotlin.ir.util.isNullable as isNullableType
import org.jetbrains.kotlin.ir.visitors.IrElementVisitorVoid
import org.jetbrains.kotlin.ir.visitors.acceptChildrenVoid
import org.jetbrains.kotlin.ir.visitors.acceptVoid
import org.jetbrains.kotlin.name.FqName

/** Closed resolved-call adapter. No native control/attribute construction or backend dependency.
 * The caller supplies ordinary language lowering and bindings for entry parameters.
 * Children are statically described; callbacks remain typed language expressions.
 */
class ComposeWidgetAdapter(private val language: Language, private val diagnostics: DiagnosticSink,
    private val sourceWidget: ((IrCall, Scope, WidgetLayoutScope?) -> Widget<EtsExpression, SourceSpan>?)? = null,
    private val pagers: Map<IrValueSymbol, ComposeStateLowering.PagerStateBinding> = emptyMap(),
    private val scrolls: Map<IrValueSymbol, ComposeStateLowering.ScrollStateBinding> = emptyMap(),
    private val lazyLists: Map<IrValueSymbol, ComposeStateLowering.LazyListStateBinding> = emptyMap(),
    private val widgetRules: List<ComposeWidgetRule> = emptyList(),
    private val sourceContent: ((IrExpression, Scope, WidgetLayoutScope?) ->
        Children<EtsExpression, SourceSpan>?)? = null) {
    constructor(language: Language, diagnostics: DiagnosticSink,
        pagers: Map<IrValueSymbol, ComposeStateLowering.PagerStateBinding>) :
        this(language, diagnostics, null, pagers, emptyMap(), emptyMap())
    constructor(language: Language, diagnostics: DiagnosticSink,
        pagers: Map<IrValueSymbol, ComposeStateLowering.PagerStateBinding>,
        scrolls: Map<IrValueSymbol, ComposeStateLowering.ScrollStateBinding>) :
        this(language, diagnostics, null, pagers, scrolls, emptyMap())
    constructor(language: Language, diagnostics: DiagnosticSink,
        pagers: Map<IrValueSymbol, ComposeStateLowering.PagerStateBinding>,
        scrolls: Map<IrValueSymbol, ComposeStateLowering.ScrollStateBinding>,
        lazyLists: Map<IrValueSymbol, ComposeStateLowering.LazyListStateBinding>) :
        this(language, diagnostics, null, pagers, scrolls, lazyLists)
    private val resolvedWidgetRules = coreComposeWidgetRules(diagnostics) + widgetRules
    private val touchBoxes = linkedMapOf<IrCall, TouchTargets>()

    fun lower(function: IrSimpleFunction, scope: Scope = Scope(),
        handledStatements: Set<IrStatement> = emptySet()): Children<EtsExpression, SourceSpan> {
        diagnostics.currentFile = sourceFile(function)?.fileEntry?.name
        if (!function.hasAnnotation(FqName("androidx.compose.runtime.Composable")) || !function.returnType.isUnit())
            diagnostics.unsupported(function, "Widget entry requires a resolved @Composable Unit function")
        function.valueParameters.forEach { parameter ->
            if (parameter.symbol !in scope.bindings && parameter.symbol !in scope.aliases)
                diagnostics.unsupported(parameter, "Widget entry parameter requires a binding: ${parameter.name}")
        }
        return body(function.body ?: diagnostics.unsupported(function, "Widget entry has no body"),
            scope.fork(), function, handledStatements, null)
    }

    fun lowerFunctionBody(function: IrFunction, scope: Scope,
        parent: WidgetLayoutScope? = null): Children<EtsExpression, SourceSpan> =
        body(function.body ?: diagnostics.unsupported(function, "Widget helper has no body"),
            scope.fork(), function, parent = parent)

    private fun body(body: IrBody, scope: Scope, owner: IrFunction,
        handledStatements: Set<IrStatement> = emptySet(), parent: WidgetLayoutScope?): Children<EtsExpression, SourceSpan> = when (body) {
        is IrBlockBody -> Children(statements(body.statements, scope, owner,
            handledStatements = handledStatements, parent = parent))
        is IrExpressionBody -> Children(statements(listOf(body.expression), scope, owner,
            handledStatements = handledStatements, parent = parent))
        else -> diagnostics.unsupported(body, "Unsupported widget body")
    }

    private fun statements(statements: List<IrStatement>, scope: Scope, owner: IrFunction, terminal: Boolean = true,
        handledStatements: Set<IrStatement> = emptySet(), parent: WidgetLayoutScope?): List<Widget<EtsExpression, SourceSpan>> {
        val result = mutableListOf<Widget<EtsExpression, SourceSpan>>()
        statements.forEachIndexed { index, statement ->
            if (statement in handledStatements) return@forEachIndexed
            if (statement is IrVariable) {
                val initial = statement.initializer ?: diagnostics.unsupported(statement, "Uninitialized widget local")
                if (statement.isVar) diagnostics.unsupported(statement, "Mutable widget local is outside the static widget subset")
                when {
                    initial.type.classFqName?.asString() in setOf("androidx.compose.ui.Modifier", "androidx.compose.ui.Modifier.Companion") ->
                        modifiers(initial, scope, parent).let {
                            scope.aliases[statement.symbol] = initial
                        }
                    resolve(initial, scope) is IrFunctionExpression -> {
                        scope.aliases[statement.symbol] = initial
                    }
                    else -> {
                        val local = language.lowerLocal(statement, scope, retainCompilerTemporary = false)
                        val reference = local.reference ?: return@forEachIndexed
                        val value = local.initializer
                            ?: diagnostics.unsupported(statement, "Uninitialized widget value binding")
                        val tail = statements.drop(index + 1)
                        val children = Children(statements(tail, scope, owner, terminal,
                            handledStatements, parent))
                        result += Widget.ValueScope(reference, value, children,
                            language.source(statement))
                        return result
                    }
                }
                return@forEachIndexed
            }
            result += when (statement) {
            is IrCall -> listOf(widget(statement, scope, parent))
            is IrWhen -> listOf(conditional(statement, scope, owner, parent))
            is IrBlock -> statements(statement.statements, scope.fork(), owner, terminal && index == statements.lastIndex,
                handledStatements, parent)
            is IrTypeOperatorCall -> when (statement.operator) {
                IrTypeOperator.IMPLICIT_COERCION_TO_UNIT -> {
                    val value = statement.argument
                    if (value is IrWhen) listOf(conditional(value, scope, owner, parent, discarded = true))
                    else statements(listOf(value), scope, owner, terminal && index == statements.lastIndex,
                        handledStatements, parent)
                }
                IrTypeOperator.IMPLICIT_CAST, IrTypeOperator.IMPLICIT_NOTNULL ->
                    statements(listOf(statement.argument), scope, owner,
                        terminal && index == statements.lastIndex, handledStatements, parent)
                else -> diagnostics.unsupported(statement,
                    "Unsupported widget type operation: ${statement.operator}")
            }
            is IrReturn -> {
                if (statement.returnTargetSymbol.owner !== owner || !terminal || index != statements.lastIndex)
                    diagnostics.unsupported(statement, "Widget return must terminate its own children body")
                statements(listOf(statement.value), scope, owner,
                    handledStatements = handledStatements, parent = parent)
            }
            is IrGetObjectValue -> if (statement.type.isUnit()) emptyList() else
                diagnostics.unsupported(statement, "Unsupported object in widget children")
            else -> diagnostics.unsupported(statement, "Unsupported widget children statement: ${statement.javaClass.simpleName}")
            }
        }
        return result
    }

    private fun conditional(value: IrWhen, scope: Scope, owner: IrFunction,
        parent: WidgetLayoutScope?, discarded: Boolean = false): Widget.Conditional<EtsExpression, SourceSpan> {
        val nullableUnit = value.type.isNullableType() && value.type.makeNotNull().isUnit()
        if (!discarded && !value.type.isUnit() && !nullableUnit)
            diagnostics.unsupported(value, "Widget conditional must produce Unit children")
        val discardBranchValues = discarded || nullableUnit
        val branches = value.branches.map { branch ->
            val condition = if (branch is IrElseBranch) null else {
                if (!branch.condition.type.isBoolean())
                    diagnostics.unsupported(branch.condition, "Widget conditional requires a Boolean condition")
                scalar(branch.condition, scope)
            }
            val nested = scope.fork()
            val result = branch.result
            val children = if (discardBranchValues && result is IrConst && result.value == null)
                Children(emptyList())
            else Children(statements(listOf(result), nested, owner, parent = parent))
            WidgetBranch(condition, children, language.source(result))
        }
        return Widget.Conditional(branches, language.source(value))
    }

    private fun repeat(call: IrCall, scope: Scope,
        parent: WidgetLayoutScope?): Widget.ForEach<EtsExpression, SourceSpan> {
        checkArguments(call, setOf("times", "action"))
        val times = argument(call, "times")
            ?: diagnostics.unsupported(call, "repeat requires times")
        if (!times.type.isInt()) diagnostics.unsupported(times, "repeat times requires Int")
        val count = scalar(times, scope)
        if (count.type != EtsTypes.NUMBER)
            diagnostics.unsupported(times, "repeat times requires target number")
        val actionExpression = argument(call, "action")
            ?: diagnostics.unsupported(call, "repeat requires action")
        val action = lambda(actionExpression, scope)
            ?: diagnostics.unsupported(actionExpression, "repeat action requires a source lambda")
        if (!action.returnType.isUnit())
            diagnostics.unsupported(action, "repeat action requires Unit result")
        val parameter = action.valueParameters.singleOrNull()
            ?: diagnostics.unsupported(action, "repeat action requires one index parameter")
        if (!parameter.type.isInt())
            diagnostics.unsupported(parameter, "repeat action index requires Int")
        val source = language.source(call)
        val item = EtsReference(EtsSymbol(
            "compose-repeat:${source.file}:${source.start}:index",
            parameter.name.asString(), EtsTypes.NUMBER, language.source(parameter)))
        val child = scope.fork().also { it.bindings[parameter.symbol] = item }
        val children = body(action.body
            ?: diagnostics.unsupported(action, "repeat action requires a body"),
            child, action, parent = parent)
        return Widget.ForEach(WidgetIterationData.Count(count), item, children, source)
    }

    private fun touchTarget(touch: TouchTargets, scope: Scope): WidgetTouchTarget<EtsExpression, SourceSpan> {
        val source = language.source(touch.box)
        fun number(value: Double): EtsExpression = EtsLiteral(value, EtsTypes.NUMBER, source)
        val item = scope.bindings[touch.index.symbol]
            ?: diagnostics.unsupported(touch.box, "Unbound repeated touch target index")
        val id = EtsBinary("+", EtsLiteral("__etsTouch${touch.box.startOffset}_",
            EtsTypes.STRING, source), item, EtsTypes.STRING, source)
        val response = WidgetRectangle(number(-touch.expandX), number(-touch.expandY),
            number(maxOf(48.0, touch.width)), number(maxOf(48.0, touch.height)), source)
        val mouse = WidgetRectangle(number(0.0), number(0.0),
            EtsLiteral("100%", EtsTypes.STRING, source),
            EtsLiteral("100%", EtsTypes.STRING, source), source)
        return WidgetTouchTarget(id, response, mouse, source)
    }

    private fun touchGroup(touch: TouchTargets, source: SourceSpan): WidgetTouchGroup<EtsExpression, SourceSpan> {
        fun number(value: Double): EtsExpression = EtsLiteral(value, EtsTypes.NUMBER, source)
        val x = maxOf(0.0, touch.expandX - touch.inset - touch.rowHorizontal)
        val y = maxOf(0.0, touch.expandY - touch.inset - touch.rowVertical)
        val response = WidgetRectangle(number(-x), number(-y),
            EtsLiteral("calc(100% + ${2 * x}vp)", EtsTypes.STRING, source),
            EtsLiteral("calc(100% + ${2 * y}vp)", EtsTypes.STRING, source), source)
        return WidgetTouchGroup(response, number(touch.inset), number(touch.width),
            number(touch.height), source)
    }

    private fun requiresMinimumTouchArbitration(
        modifiers: List<WidgetModifier<EtsExpression, SourceSpan>>): Boolean {
        if (modifiers.none { it is WidgetModifier.Click } ||
            modifiers.any { it is WidgetModifier.Click && it.touchTarget != null }) return false
        fun constant(value: EtsExpression): Double? =
            ((value as? EtsLiteral)?.value as? Number)?.toDouble()
        var width: Double? = null
        var height: Double? = null
        modifiers.forEach { modifier -> when (modifier) {
            is WidgetModifier.Size -> {
                width = constant(modifier.width)
                height = constant(modifier.height)
            }
            is WidgetModifier.Width -> width = constant(modifier.value)
            is WidgetModifier.Height -> height = constant(modifier.value)
            else -> Unit
        } }
        return width?.let { it < 48.0 } == true || height?.let { it < 48.0 } == true
    }

    private fun widget(call: IrCall, scope: Scope, parent: WidgetLayoutScope?): Widget<EtsExpression, SourceSpan> {
        if (symbolName(call.symbol.owner) == "kotlin.repeat") return repeat(call, scope, parent)
        val services = object : ComposeWidgetServices {
            override fun content(expression: IrExpression, scope: Scope,
                parent: WidgetLayoutScope?,
                arguments: List<EtsExpression>): Children<EtsExpression, SourceSpan> {
                val function = lambda(expression, scope)
                if (function == null) {
                    if (arguments.isNotEmpty()) diagnostics.unsupported(expression,
                        "Parameterized widget content requires a structured lambda")
                    return sourceContent?.invoke(expression, scope, parent)
                        ?: diagnostics.unsupported(expression, "Widget content requires a structured lambda or slot")
                }
                if (function.valueParameters.size != arguments.size)
                    diagnostics.unsupported(expression,
                        "Widget content requires ${function.valueParameters.size} arguments, got ${arguments.size}")
                val childScope = scope.fork()
                function.valueParameters.zip(arguments).forEach { (parameter, value) ->
                    childScope.bindings[parameter.symbol] = value
                }
                return body(function.body ?: diagnostics.unsupported(expression, "Widget content has no body"),
                    childScope, function, parent = parent)
            }

            override val parent: WidgetLayoutScope? = parent

            override fun modifiers(expression: IrExpression?, scope: Scope,
                parent: WidgetLayoutScope?): List<WidgetModifier<EtsExpression, SourceSpan>> =
                this@ComposeWidgetAdapter.modifiers(expression, scope, parent)

            override fun value(expression: IrExpression, scope: Scope,
                type: WidgetValueType): WidgetValue<EtsExpression, SourceSpan> =
                widgetValue(expression, scope, type)
        }
        resolvedWidgetRules.firstNotNullOfOrNull { it.lower(call, language, scope, services) }?.let { return it }
        sourceWidget?.invoke(call, scope, parent)?.let { return it }
        val api = symbolName(call.symbol.owner)
        if (sourceFile(call.symbol.owner) != null || !call.type.isUnit() || api !in supported)
            diagnostics.unsupported(call, "Unsupported resolved widget API: $api")
        val sourceTouchGroup = if (api == "androidx.compose.foundation.layout.Row")
            touchTargets(call, scope, diagnostics) else null
        sourceTouchGroup?.let { touchBoxes[it.box] = it }
        val text = api.endsWith(".Text")
        val button = api.endsWith("Button")
        val image = api in setOf("androidx.compose.foundation.Image", "coil.compose.AsyncImage")
        val textField = api.endsWith("TextField")
        val isPager = api == "androidx.compose.foundation.pager.HorizontalPager"
        val isLazyList = api in setOf("androidx.compose.foundation.lazy.LazyColumn",
            "androidx.compose.foundation.lazy.LazyRow")
        val richTextStyle = language.callRules.any { it is ComposeTextStyleRule }
        checkArguments(call, when {
            text -> setOf("text", "modifier", "fontSize", "fontWeight", "fontFamily", "lineHeight") +
                if (richTextStyle) setOf("minLines", "softWrap") + textStyleArgumentOrder else emptySet()
            button -> if (api in setOf("androidx.compose.material3.Button",
                    "androidx.compose.material3.TextButton"))
                setOf("onClick", "enabled", "modifier", "content", "colors", "shape",
                    "contentPadding", "border")
            else setOf("onClick", "enabled", "modifier", "content")
            image -> if (api == "androidx.compose.foundation.Image")
                setOf("painter", "contentDescription", "modifier")
            else setOf("model", "contentDescription", "modifier")
            textField -> setOf("value", "onValueChange", "modifier", "enabled")
            isPager -> setOf("state", "modifier", "pageContent", "userScrollEnabled", "flingBehavior",
                "snapPosition")
            isLazyList -> setOf("modifier", "state", "content", "userScrollEnabled")
            api.endsWith(".Row") -> setOf("modifier", "horizontalArrangement", "verticalAlignment", "content")
            api.endsWith(".Column") -> setOf("modifier", "verticalArrangement", "horizontalAlignment", "content")
            api.endsWith(".Box") -> setOf("modifier", "contentAlignment", "content")
            else -> setOf("modifier", "content")
        })
        val source = language.source(call)
        val rawModifiers = modifiers(argument(call, "modifier"), scope, parent)
        val boxTouch = if (api == "androidx.compose.foundation.layout.Box") touchBoxes[call] else null
        val modifier = if (boxTouch == null) rawModifiers else rawModifiers.map { operation ->
            if (operation is WidgetModifier.Click) operation.copy(touchTarget = touchTarget(boxTouch, scope))
            else operation
        }
        if (api == "androidx.compose.foundation.layout.Box" && boxTouch == null &&
            requiresMinimumTouchArbitration(modifier))
            diagnostics.unsupported(call,
                "Minimum touch target arbitration requires a bounded homogeneous sibling group")
        fun required(name: String) = argument(call, name)
            ?: diagnostics.unsupported(call, "$api requires $name")
        if (text) {
            val value = required("text")
            if (!value.type.isString()) diagnostics.unsupported(value, "Widget Text requires String text")
            fun style(name: String, sourceType: String, targetType: WidgetValueType): WidgetValue<EtsExpression, SourceSpan>? =
                argument(call, name)?.let {
                    val actual = it.type.classFqName?.asString()
                    val matches = actual == sourceType || sourceType == "androidx.compose.ui.text.font.FontFamily" &&
                        actual?.startsWith("androidx.compose.ui.text.font.") == true && actual.endsWith("FontFamily")
                    if (!matches)
                        diagnostics.unsupported(it, "Widget Text $name requires $sourceType")
                    widgetValue(it, scope, targetType)
                }
            val textValue = widgetValue(value, scope, WidgetValueType.STRING)
            val fontSize = style("fontSize", "androidx.compose.ui.unit.TextUnit", WidgetValueType.FONT_SIZE)
            val fontWeight = style("fontWeight", "androidx.compose.ui.text.font.FontWeight", WidgetValueType.FONT_WEIGHT)
            val fontFamily = style("fontFamily", "androidx.compose.ui.text.font.FontFamily", WidgetValueType.FONT_FAMILY)
            val lineHeight = style("lineHeight", "androidx.compose.ui.unit.TextUnit", WidgetValueType.LINE_HEIGHT)
            val color = argument(call, "color")?.let { widgetValue(it, scope, WidgetValueType.COLOR) }
            fun expression(name: String): EtsExpression? = argument(call, name)?.let { scalar(it, scope) }
            val fontStyle = expression("fontStyle")
            val letterSpacing = expression("letterSpacing")
            val textDecoration = expression("textDecoration")
            val textAlign = expression("textAlign")
            val overflow = expression("overflow")
            val maxLines = expression("maxLines")
            val providedStyle = argument(call, "style")?.let { scalar(it, scope) }
            val ambient = if (api == "androidx.compose.material3.Text")
                scope.ambientValues[MATERIAL_CONTEXT] else null
            val inherited = when {
                api == "androidx.compose.material3.Text" && ambient != null -> {
                    val base = materialCurrentTextStyle(ambient, source)
                    argument(call, "style")?.let {
                        mergeTextStyles(base, checkNotNull(providedStyle), language.source(it))
                    } ?: base
                }
                api == "androidx.compose.material3.Text" && richTextStyle -> {
                    val base = defaultTypographyRole("bodyLarge", source)
                    argument(call, "style")?.let {
                        mergeTextStyles(base, checkNotNull(providedStyle), language.source(it))
                    } ?: base
                }
                providedStyle != null -> providedStyle
                else -> null
            }
            val style = WidgetTextStyle(
                fontSize, fontWeight, fontFamily, lineHeight, color,
                fontStyle, letterSpacing, textDecoration, textAlign, overflow, maxLines, inherited,
                WidgetValue(WidgetValueType.COLOR,
                    ambient?.let { materialContentColor(it, source) }
                        ?: EtsLiteral(0xFF000000L, EtsTypes.NUMBER, source),
                    WidgetValueProvenance.Expression(null), source))
            val valuesByName = mapOf<String, EtsExpression?>(
                "text" to textValue.value, "fontSize" to fontSize?.value,
                "fontWeight" to fontWeight?.value, "fontFamily" to fontFamily?.value,
                "lineHeight" to lineHeight?.value, "color" to color?.value,
                "fontStyle" to fontStyle, "letterSpacing" to letterSpacing,
                "textDecoration" to textDecoration, "textAlign" to textAlign,
                "overflow" to overflow, "maxLines" to maxLines, "style" to providedStyle)
            val sourceEvaluations = valuesByName.mapNotNull { (name, emitted) ->
                val input = argument(call, name)
                if (input == null || emitted == null) null else language.source(input).start to emitted
            }.sortedBy { it.first }.map { it.second }
            return Widget.Text(textValue, style, modifier, source, sourceEvaluations)
        }
        if (image) return image(call, api, scope, modifier, source)
        if (isPager) return pager(call, scope, modifier, source)
        if (isLazyList) return lazyList(call, api, scope, modifier, source)
        if (api == "androidx.compose.foundation.layout.Spacer") return Widget.Spacer(modifier, source)
        if (textField) {
            val value = required("value")
            if (!value.type.isString()) diagnostics.unsupported(value,
                "Widget TextField requires a String value; rich text values are outside this subset")
            val enabled = argument(call, "enabled")?.let {
                if (!it.type.isBoolean()) diagnostics.unsupported(it, "Widget TextField enabled requires Boolean")
                scalar(it, scope)
            }
            return Widget.TextField(scalar(value, scope),
                event(required("onValueChange"), scope,
                    EtsFunctionType(listOf(EtsTypes.STRING), EtsTypes.VOID), "TextField onValueChange"),
                enabled, modifier, source)
        }
        // A slot owns its nested scope; siblings never inherit bindings from its content.
        val content = argument(call, "content")
        val childScope = scope.fork()
        var buttonStyle: WidgetButtonStyle<EtsExpression, SourceSpan>? = null
        if (button && api.startsWith("androidx.compose.material3.")) {
            val context = materialInvocationContext(scope, source)
            if (context != null) {
                val enabled = argument(call, "enabled")?.let { scalar(it, scope) }
                    ?: EtsLiteral(true, EtsTypes.BOOLEAN, source)
                val materialButton = api in setOf("androidx.compose.material3.Button",
                    "androidx.compose.material3.TextButton")
                val palette = if (materialButton) argument(call, "colors")?.let { scalar(it, scope) }
                    ?: defaultButtonColors(scope, source, api.endsWith("TextButton")) else null
                fun selected(name: String): EtsExpression = EtsConditional(enabled,
                    EtsMember(requireNotNull(palette), name, EtsTypes.NUMBER, source),
                    EtsMember(requireNotNull(palette),
                        "disabled" + name.replaceFirstChar { it.uppercaseChar() }, EtsTypes.NUMBER, source),
                    EtsTypes.NUMBER, source)
                val contentColor = if (materialButton) selected("contentColor")
                    else materialContentColor(context, source)
                if (materialButton) {
                    val textual = api.endsWith("TextButton")
                    buttonStyle = WidgetButtonStyle(
                        WidgetValue(WidgetValueType.COLOR, selected("containerColor"),
                            WidgetValueProvenance.Expression(null), source),
                        argument(call, "contentPadding")?.let { scalar(it, scope) }
                            ?: symmetricPadding(EtsLiteral(if (textual) 12 else 24, EtsTypes.NUMBER, source),
                                EtsLiteral(8, EtsTypes.NUMBER, source), source),
                        argument(call, "shape")?.let { shapeRadius(it, scope) }
                            ?: EtsLiteral("50%", EtsTypes.STRING, source),
                        argument(call, "border")?.let { scalar(it, scope) },
                        EtsLiteral(58, EtsTypes.NUMBER, source),
                        EtsLiteral(40, EtsTypes.NUMBER, source), textual, source)
                }
                childScope.ambientValues[MATERIAL_CONTEXT] = newMaterialContext(source,
                    MaterialContextField.COLOR_SCHEME to materialScheme(context, source),
                    MaterialContextField.CONTENT_COLOR to contentColor,
                    MaterialContextField.TYPOGRAPHY to materialTypography(context, source),
                    MaterialContextField.TEXT_STYLE to if (api.endsWith("IconButton"))
                        materialCurrentTextStyle(context, source)
                    else EtsMember(materialTypography(context, source), "labelLarge", textStyleType, source),
                    MaterialContextField.SHAPES to materialShapes(context, source))
            }
        }
        val children = if (content == null && api == "androidx.compose.foundation.layout.Box" &&
            call.symbol.owner.valueParameters.none { it.name.asString() == "content" }) Children(emptyList()) else {
            val value = content ?: diagnostics.unsupported(call, "$api requires content")
            val childParent = when {
                button || api.endsWith(".Row") -> WidgetLayoutScope.ROW
                api.endsWith(".Column") -> WidgetLayoutScope.COLUMN
                else -> WidgetLayoutScope.BOX
            }
            services.content(value, childScope, childParent)
        }
        return when {
            button -> Widget.Button(event(required("onClick"), scope,
                EtsFunctionType(emptyList(), EtsTypes.VOID), "callback"), argument(call, "enabled")?.let {
                if (!it.type.isBoolean()) diagnostics.unsupported(it, "Widget Button enabled requires Boolean")
                scalar(it, scope)
            }, children, modifier, source, if (api.endsWith("IconButton"))
                WidgetButtonRole.ICON else WidgetButtonRole.DEFAULT, buttonStyle)
            api.endsWith(".Row") -> Widget.Row(children, modifier, source,
                sourceTouchGroup?.let { touchGroup(it, source) },
                mainAxisArrangement(argument(call, "horizontalArrangement"), scope),
                argument(call, "verticalAlignment")?.let { scalar(it, scope) })
            api.endsWith(".Column") -> Widget.Column(children, modifier, source,
                mainAxisArrangement(argument(call, "verticalArrangement"), scope),
                argument(call, "horizontalAlignment")?.let { scalar(it, scope) })
            else -> Widget.Box(children, modifier, source,
                argument(call, "contentAlignment")?.let { scalar(it, scope) })
        }
    }

    private fun mainAxisArrangement(value: IrExpression?, scope: Scope):
        WidgetMainAxisArrangement<EtsExpression, SourceSpan>? = value?.let {
        val source = language.source(it)
        val fixed = arrangementAlignmentName(it, scope)
        if (fixed != null) WidgetMainAxisArrangement.Alignment(when (fixed) {
            "Start" -> WidgetMainAxisAlignment.START
            "Center" -> WidgetMainAxisAlignment.CENTER
            "End" -> WidgetMainAxisAlignment.END
            "SpaceBetween" -> WidgetMainAxisAlignment.SPACE_BETWEEN
            "SpaceAround" -> WidgetMainAxisAlignment.SPACE_AROUND
            "SpaceEvenly" -> WidgetMainAxisAlignment.SPACE_EVENLY
            else -> error("Unsupported fixed arrangement: $fixed")
        }, source) else WidgetMainAxisArrangement.Spacing(arrangementSpace(scalar(it, scope)), source)
    }

    private fun pager(call: IrCall, scope: Scope,
        modifiers: List<WidgetModifier<EtsExpression, SourceSpan>>,
        source: SourceSpan): Widget.Pager<EtsExpression, SourceSpan> {
        validatePagerBehavior(call, scope, diagnostics)
        val state = argument(call, "state")
            ?: diagnostics.unsupported(call, "HorizontalPager requires state")
        val holder = (resolve(state, scope) as? IrGetValue)?.symbol
        val binding = holder?.let(pagers::get)
            ?: diagnostics.unsupported(state, "HorizontalPager state requires source remembered PagerState")
        val enabled = argument(call, "userScrollEnabled")?.let { value ->
            if (!value.type.isBoolean()) diagnostics.unsupported(value,
                "HorizontalPager userScrollEnabled requires Boolean")
            scalar(value, scope)
        } ?: EtsLiteral(true, EtsTypes.BOOLEAN, source)
        val content = argument(call, "pageContent")
            ?: diagnostics.unsupported(call, "HorizontalPager requires pageContent")
        val lambda = resolve(content, scope) as? IrFunctionExpression
            ?: diagnostics.unsupported(content, "HorizontalPager pageContent requires a direct lambda")
        val parameter = lambda.function.valueParameters.singleOrNull()
            ?: diagnostics.unsupported(content, "HorizontalPager pageContent requires one page index parameter")
        if (!parameter.type.isInt() || !lambda.function.returnType.isUnit())
            diagnostics.unsupported(parameter, "HorizontalPager pageContent requires an Int page index and Unit result")
        val indexSymbol = EtsSymbol("compose-pager:${source.file}:${source.start}:page",
            parameter.name.asString(), EtsTypes.NUMBER, language.source(parameter))
        val index = EtsReference(indexSymbol)
        val childScope = scope.fork().also { it.bindings[parameter.symbol] = index }
        val children = body(lambda.function.body
            ?: diagnostics.unsupported(content, "HorizontalPager pageContent has no body"),
            childScope, lambda.function, parent = null)
        val changeSymbol = EtsSymbol("compose-pager:${source.file}:${source.start}:change",
            "index", EtsTypes.NUMBER, source)
        val onPageChange = EtsLambda(listOf(EtsParameter(changeSymbol)), listOf(EtsExpressionStatement(
            EtsAssignment(binding.currentPage, EtsReference(changeSymbol), source))), EtsTypes.VOID, source)
        return Widget.Pager(binding.currentPage, binding.pageCount, binding.controller, enabled, onPageChange,
            IndexedChildren(index, children, language.source(content)), modifiers, source)
    }

    private fun lazyList(call: IrCall, api: String, scope: Scope,
        modifiers: List<WidgetModifier<EtsExpression, SourceSpan>>,
        source: SourceSpan): Widget.LazyList<EtsExpression, SourceSpan> {
        val content = argument(call, "content")
            ?: diagnostics.unsupported(call, "$api requires content")
        val lambda = lambda(content, scope)
            ?: diagnostics.unsupported(content, "$api content requires a direct lambda")
        if (lambda.valueParameters.isNotEmpty() || !lambda.returnType.isUnit())
            diagnostics.unsupported(lambda, "$api content requires a LazyListScope receiver and Unit result")
        val enabled = argument(call, "userScrollEnabled")?.let { value ->
            if (!value.type.isBoolean()) diagnostics.unsupported(value, "$api userScrollEnabled requires Boolean")
            scalar(value, scope)
        } ?: EtsLiteral(true, EtsTypes.BOOLEAN, source)
        val state = argument(call, "state")?.let { value ->
            val holder = (resolve(value, scope) as? IrGetValue)?.symbol
            val binding = holder?.let(lazyLists::get)
                ?: diagnostics.unsupported(value,
                    "$api state requires source remembered LazyListState")
            LazyListState(binding.initialIndex, binding.initialOffset, binding.firstVisibleIndex,
                binding.controller, binding.initialOffsetApplied, binding.source)
        }
        val slots = lazyListBody(lambda.body
            ?: diagnostics.unsupported(content, "$api content has no body"), scope.fork(), lambda)
        return Widget.LazyList(
            if (api.endsWith("LazyColumn")) WidgetScrollAxis.VERTICAL else WidgetScrollAxis.HORIZONTAL,
            enabled, state, slots, modifiers, source)
    }

    private fun lazyListBody(value: IrBody, scope: Scope,
        owner: IrFunction): List<LazyListSlot<EtsExpression, SourceSpan>> = when (value) {
        is IrBlockBody -> value.statements.flatMap { lazyListStatement(it, scope, owner) }
        is IrExpressionBody -> lazyListStatement(value.expression, scope, owner)
        else -> diagnostics.unsupported(value, "Unsupported lazy list content body")
    }

    private fun lazyListStatement(value: IrStatement, scope: Scope,
        owner: IrFunction): List<LazyListSlot<EtsExpression, SourceSpan>> = when (value) {
        is IrReturn -> {
            if (value.returnTargetSymbol.owner !== owner)
                diagnostics.unsupported(value, "Lazy list return must target its content lambda")
            lazyListStatement(value.value, scope, owner)
        }
        is IrBlock -> value.statements.flatMap { lazyListStatement(it, scope.fork(), owner) }
        is IrComposite -> value.statements.flatMap { lazyListStatement(it, scope, owner) }
        is IrGetObjectValue -> if (value.type.isUnit()) emptyList() else
            diagnostics.unsupported(value, "Unexpected lazy list value")
        is IrCall -> listOf(lazyListCall(value, scope))
        else -> diagnostics.unsupported(value,
            "Unsupported lazy list statement: ${value.javaClass.simpleName}")
    }

    private fun lazyListCall(call: IrCall, scope: Scope): LazyListSlot<EtsExpression, SourceSpan> {
        val api = symbolName(call.symbol.owner)
        val source = language.source(call)
        fun content(name: String = "content"): IrFunction {
            val value = argument(call, name)
                ?: diagnostics.unsupported(call, "$api requires $name")
            return lambda(value, scope)
                ?: diagnostics.unsupported(value, "$api $name requires a direct lambda")
        }
        fun rejectReceiverUse(function: IrFunction) {
            function.extensionReceiverParameter?.let { receiver ->
                var animateItem: IrCall? = null
                (function.body ?: function).acceptVoid(object : IrElementVisitorVoid {
                    override fun visitElement(element: IrElement) = element.acceptChildrenVoid(this)
                    override fun visitCall(expression: IrCall) {
                        if (symbolName(expression.symbol.owner).endsWith(".animateItem")) animateItem = expression
                        expression.acceptChildrenVoid(this)
                    }
                })
                animateItem?.let { diagnostics.unsupported(it, "LazyItemScope animateItem is not supported") }
                if (used(receiver, function.body ?: function))
                    diagnostics.unsupported(receiver, "LazyItemScope APIs are not supported")
            }
        }
        fun keyValue(value: IrExpression, keyScope: Scope): EtsExpression? {
            val resolved = resolve(value, keyScope)
            if (resolved is IrConst && resolved.value == null) return null
            val emitted = scalar(resolved, keyScope)
            if (emitted.type !in setOf(EtsTypes.STRING, EtsTypes.NUMBER))
                diagnostics.unsupported(value, "Lazy list key requires a stable String or Int value")
            return emitted
        }
        if (api in setOf("androidx.compose.foundation.lazy.LazyListScope.item",
                "androidx.compose.foundation.lazy.item")) {
            checkArguments(call, setOf("key", "content"))
            val itemContent = content()
            if (itemContent.valueParameters.isNotEmpty() || !itemContent.returnType.isUnit())
                diagnostics.unsupported(itemContent, "Lazy list item content requires no value parameters and Unit result")
            rejectReceiverUse(itemContent)
            val children = body(itemContent.body
                ?: diagnostics.unsupported(itemContent, "Lazy list item content has no body"),
                scope.fork(), itemContent, parent = null)
            val key = argument(call, "key")?.let { keyValue(it, scope) }
            return LazyListSlot.Item(key, children, source)
        }
        val indexed = api in setOf("androidx.compose.foundation.lazy.itemsIndexed",
            "androidx.compose.foundation.lazy.LazyListScope.itemsIndexed")
        val ordinary = api in setOf("androidx.compose.foundation.lazy.items",
            "androidx.compose.foundation.lazy.LazyListScope.items")
        if (!indexed && !ordinary)
            diagnostics.unsupported(call, "Unsupported lazy list DSL: $api")
        checkArguments(call, setOf("items", "count", "key", "itemContent"))
        val count = argument(call, "count")
        val values = argument(call, "items")
        if (indexed && count != null)
            diagnostics.unsupported(count, "itemsIndexed does not support a count source")
        if ((count == null) == (values == null))
            diagnostics.unsupported(call, "$api requires exactly one items or count source")
        val itemContent = content("itemContent")
        rejectReceiverUse(itemContent)
        if (!itemContent.returnType.isUnit())
            diagnostics.unsupported(itemContent, "$api itemContent requires Unit result")
        val parameters = itemContent.valueParameters
        val expected = if (indexed) 2 else 1
        if (parameters.size != expected)
            diagnostics.unsupported(itemContent, "$api itemContent requires $expected value parameter(s)")

        val sourceIndex = if (indexed) parameters[0] else if (count != null) parameters[0] else null
        val sourceItem = if (indexed) parameters[1] else if (values != null) parameters[0] else null
        sourceIndex?.let { if (!it.type.isInt()) diagnostics.unsupported(it, "$api index requires Int") }
        val loweredValues = values?.let { value ->
            val sourceType = value.type.classFqName?.asString()
            if (sourceType !in lazyCollectionTypes)
                diagnostics.unsupported(value, "$api requires a List or array source")
            language.expression(value, scope).also { emitted ->
                val type = emitted.type as? EtsNamedType
                if (type?.name != "Array" || type.arguments.size != 1)
                    diagnostics.unsupported(value, "$api collection requires target Array lowering")
            }
        }
        val loweredCount = count?.let { value ->
            if (!value.type.isInt()) diagnostics.unsupported(value, "$api count requires Int")
            scalar(value, scope)
        }
        val itemType = loweredValues?.let { (it.type as EtsNamedType).arguments.single() } ?: EtsTypes.NUMBER
        sourceItem?.let { parameter ->
            if (language.type(parameter.type) != itemType)
                diagnostics.unsupported(parameter, "$api item parameter differs from its collection element")
        }
        val itemName = sourceItem?.name?.asString() ?: "__lazyItem"
        val indexName = sourceIndex?.name?.asString()?.takeUnless { it == itemName } ?: "__lazyIndex"
        val item = EtsSymbol("compose-lazy:${source.file}:${source.start}:item", itemName,
            itemType, source)
        val index = EtsSymbol("compose-lazy:${source.file}:${source.start}:index", indexName,
            EtsTypes.NUMBER, source)
        val itemRef = EtsReference(item)
        val indexRef = EtsReference(index)
        val childScope = scope.fork().also { nested ->
            sourceItem?.let { nested.bindings[it.symbol] = itemRef }
            sourceIndex?.let { nested.bindings[it.symbol] = indexRef }
        }
        val children = body(itemContent.body
            ?: diagnostics.unsupported(itemContent, "$api itemContent has no body"),
            childScope, itemContent, parent = null)
        val key = argument(call, "key")?.let { keyExpression ->
            val keyLambda = lambda(keyExpression, scope)
                ?: diagnostics.unsupported(keyExpression, "$api key requires a direct lambda")
            val keyParameters = keyLambda.valueParameters
            if (keyParameters.size != expected)
                diagnostics.unsupported(keyLambda, "$api key requires $expected value parameter(s)")
            val keyScope = scope.fork()
            if (indexed) {
                keyScope.bindings[keyParameters[0].symbol] = indexRef
                keyScope.bindings[keyParameters[1].symbol] = itemRef
            } else {
                keyScope.bindings[keyParameters[0].symbol] = if (count != null) indexRef else itemRef
            }
            keyValue(lambdaResult(keyLambda), keyScope)
        }
        val data = loweredValues?.let { LazyListData.Values(it) }
            ?: LazyListData.Count(checkNotNull(loweredCount))
        return LazyListSlot.Items(data, itemRef, indexRef, key, children, source)
    }

    private fun lambdaResult(function: IrFunction): IrExpression {
        val value = when (val body = function.body) {
            is IrExpressionBody -> body.expression
            is IrBlockBody -> (body.statements.singleOrNull() as? IrReturn)?.takeIf {
                it.returnTargetSymbol.owner === function
            }?.value
            else -> null
        }
        return value ?: diagnostics.unsupported(function,
            "Lazy list key requires a single expression result")
    }

    private fun used(parameter: IrValueParameter, element: IrElement): Boolean {
        var found = false
        element.acceptVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) {
                if (!found) element.acceptChildrenVoid(this)
            }
            override fun visitGetValue(expression: IrGetValue) {
                if (expression.symbol == parameter.symbol) found = true
                if (!found) expression.acceptChildrenVoid(this)
            }
        })
        return found
    }

    private fun image(call: IrCall, api: String, scope: Scope,
        modifiers: List<WidgetModifier<EtsExpression, SourceSpan>>, source: SourceSpan): Widget.Image<EtsExpression, SourceSpan> {
        fun required(name: String) = argument(call, name)
            ?: diagnostics.unsupported(call, "$api requires $name")
        val description = scalarImageDescription(required("contentDescription"), scope)
        val image = if (api == "androidx.compose.foundation.Image") {
            val painter = required("painter")
            val resolved = resolve(painter, scope) as? IrCall
                ?: diagnostics.unsupported(painter, "Widget Image requires direct painterResource; arbitrary Painter is unsupported")
            if (symbolName(resolved.symbol.owner) != "androidx.compose.ui.res.painterResource")
                diagnostics.unsupported(painter, "Widget Image requires direct painterResource; arbitrary Painter is unsupported")
            val value = language.expression(resolved, scope)
            val expected = EtsNamedType("Resource", external = true)
            if (value.type != expected) diagnostics.unsupported(painter,
                "Widget painterResource requires a materialized Resource value")
            ImageSource.Resource(value, language.source(resolved))
        } else {
            val model = required("model")
            if (!model.type.isString()) diagnostics.unsupported(model,
                "Widget AsyncImage requires a String URL; request and painter models are unsupported")
            val value = scalar(model, scope)
            val address = (value as? EtsLiteral)?.value as? String
            if (address != null) {
                val uri = runCatching { URI(address) }.getOrNull()
                if (uri == null || uri.scheme !in setOf("http", "https") || uri.host.isNullOrBlank() || uri.userInfo != null)
                    diagnostics.unsupported(model, "Widget AsyncImage requires an HTTP(S) URL without embedded credentials")
            }
            ImageSource.Url(value, language.source(model))
        }
        return Widget.Image(image, description, modifiers, source)
    }

    private fun scalarImageDescription(value: IrExpression, scope: Scope): EtsExpression {
        val emitted = scalar(value, scope)
        if (emitted.type !in setOf(EtsTypes.STRING, EtsTypes.NULL)) diagnostics.unsupported(value,
            "Widget Image contentDescription requires a non-null String or explicit null")
        return emitted
    }

    private fun modifiers(value: IrExpression?, scope: Scope,
        parent: WidgetLayoutScope?): List<WidgetModifier<EtsExpression, SourceSpan>> {
        val expression = value?.let { resolve(it, scope) } ?: return emptyList()
        if (expression is IrGetValue && scope.bindings[expression.symbol]?.type == emptyModifierType)
            return emptyList()
        if (expression is IrGetObjectValue &&
            symbolName(expression.symbol.owner) == "androidx.compose.ui.Modifier.Companion") return emptyList()
        if (expression is IrWhen) return conditionalModifiers(expression, scope, parent)
        val call = expression as? IrCall ?: diagnostics.unsupported(expression, "Unsupported widget Modifier value")
        val api = symbolName(call.symbol.owner)
        if (api == "kotlin.let") return modifierLet(call, scope, parent)
        if (api.endsWith(".animateItem"))
            diagnostics.unsupported(call, "LazyItemScope animateItem is not supported")
        if (call.symbol.owner.dispatchReceiverParameter?.type?.classFqName?.asString() ==
            "androidx.compose.foundation.lazy.LazyItemScope")
            diagnostics.unsupported(call, "LazyItemScope modifier APIs are not supported")
        val receiver = call.extensionReceiver ?: call.dispatchReceiver
            ?: diagnostics.unsupported(call, "Widget Modifier requires a receiver")
        val previous = modifiers(receiver, scope, parent)
        if (api == "androidx.compose.ui.Modifier.then") {
            checkArguments(call, setOf("other"))
            return previous + modifiers(argument(call, "other") ?: diagnostics.unsupported(call, "Modifier.then requires other"),
                scope, parent)
        }
        if (api == "androidx.compose.foundation.layout.safeDrawingPadding") {
            checkArguments(call, emptySet())
            return previous
        }
        val at = language.source(call)
        fun dimension(value: IrExpression): EtsExpression {
            if (value.type.classFqName?.asString() != "androidx.compose.ui.unit.Dp")
                diagnostics.unsupported(value, "Widget dimension requires Dp")
            val emitted = requireSpecifiedDp(scalar(value, scope), language.source(value), "Widget dimension")
            val constant = (emitted as? EtsLiteral)?.value as? Number
            if (constant != null && (!constant.toDouble().isFinite() || constant.toDouble() < 0))
                diagnostics.unsupported(value, "Widget dimension must be finite and non-negative")
            return emitted
        }
        fun required(name: String) = argument(call, name) ?: diagnostics.unsupported(call, "$api requires $name")
        val operation: WidgetModifier<EtsExpression, SourceSpan> = when (api) {
            "androidx.compose.foundation.layout.size" -> {
                checkArguments(call, setOf("size", "width", "height"))
                val uniform = argument(call, "size")
                WidgetModifier.Size(
                    dimension(uniform ?: required("width")),
                    dimension(uniform ?: required("height")), at)
            }
            "androidx.compose.foundation.layout.width" -> {
                checkArguments(call, setOf("width")); WidgetModifier.Width(dimension(required("width")), at)
            }
            "androidx.compose.foundation.layout.height" -> {
                checkArguments(call, setOf("height")); WidgetModifier.Height(dimension(required("height")), at)
            }
            "androidx.compose.foundation.layout.fillMaxWidth",
            "androidx.compose.foundation.layout.fillMaxHeight",
            "androidx.compose.foundation.layout.fillMaxSize" -> {
                checkArguments(call, setOf("fraction"))
                val fraction = argument(call, "fraction")?.let { value ->
                    val emitted = scalar(value, scope)
                    if (emitted.type != EtsTypes.NUMBER)
                        diagnostics.unsupported(value, "Widget fill fraction requires Float")
                    val constant = (emitted as? EtsLiteral)?.value as? Number
                    if (constant != null && (!constant.toDouble().isFinite() || constant.toDouble() !in 0.0..1.0))
                        diagnostics.unsupported(value, "Widget fill fraction must be finite and between zero and one")
                    emitted
                } ?: EtsLiteral(1.0, EtsTypes.NUMBER, at)
                WidgetModifier.Fill(api != "androidx.compose.foundation.layout.fillMaxHeight",
                    api != "androidx.compose.foundation.layout.fillMaxWidth", fraction, at)
            }
            "androidx.compose.foundation.layout.RowScope.weight",
            "androidx.compose.foundation.layout.ColumnScope.weight" -> {
                checkArguments(call, setOf("weight", "fill"))
                val requiredParent = if (api.contains("RowScope")) WidgetLayoutScope.ROW else WidgetLayoutScope.COLUMN
                if (parent != requiredParent) diagnostics.unsupported(call,
                    "Widget weight requires a direct ${requiredParent.name.lowercase().replaceFirstChar(Char::uppercase)} parent")
                argument(call, "fill")?.let { fill ->
                    if ((scalar(fill, scope) as? EtsLiteral)?.value != true)
                        diagnostics.unsupported(fill, "Widget weight requires fill=true")
                }
                val value = required("weight")
                val emitted = scalar(value, scope)
                if (emitted.type != EtsTypes.NUMBER) diagnostics.unsupported(value, "Widget weight requires Float")
                val constant = (emitted as? EtsLiteral)?.value as? Number
                if (constant != null && (!constant.toDouble().isFinite() || constant.toDouble() <= 0.0))
                    diagnostics.unsupported(value, "Widget weight must be finite and positive")
                WidgetModifier.Weight(emitted, requiredParent, at)
            }
            "androidx.compose.foundation.layout.BoxScope.align" -> {
                checkArguments(call, setOf("alignment"))
                if (parent != WidgetLayoutScope.BOX)
                    diagnostics.unsupported(call, "Widget align requires a direct Box parent")
                val alignment = required("alignment")
                val emitted = language.expression(resolve(alignment, scope), scope)
                if (emitted.type != EtsNamedType("Alignment"))
                    diagnostics.unsupported(alignment, "Widget align requires Alignment")
                WidgetModifier.Align(emitted, WidgetLayoutScope.BOX, at)
            }
            "androidx.compose.foundation.layout.padding" -> {
                checkArguments(call, setOf("all", "horizontal", "vertical", "start", "top", "end", "bottom",
                    "paddingValues"))
                if (call.symbol.owner.valueParameters.any { it.name.asString() == "paddingValues" }) {
                    val value = required("paddingValues")
                    val emitted = scalar(value, scope)
                    if (emitted.type != paddingType)
                        diagnostics.unsupported(value, "Widget paddingValues requires PaddingValues")
                    WidgetModifier.PaddingValues(emitted, at)
                } else {
                    fun side(name: String, axis: String) =
                        (argument(call, "all") ?: argument(call, name) ?: argument(call, axis))
                            ?.let(::dimension) ?: EtsLiteral(0, EtsTypes.NUMBER, at)
                    WidgetModifier.Padding(side("start", "horizontal"), side("top", "vertical"),
                        side("end", "horizontal"), side("bottom", "vertical"), at)
                }
            }
            "androidx.compose.foundation.background" -> {
                checkArguments(call, setOf("color", "shape"))
                val color = required("color")
                WidgetModifier.Background(widgetValue(color, scope, WidgetValueType.COLOR), at,
                    argument(call, "shape")?.let { shapeRadius(it, scope) })
            }
            "androidx.compose.ui.draw.clip" -> {
                checkArguments(call, setOf("shape"))
                WidgetModifier.Clip(shapeRadius(required("shape"), scope), at)
            }
            "androidx.compose.ui.platform.testTag" -> {
                checkArguments(call, setOf("tag"))
                val tag = required("tag")
                if (!tag.type.isString()) diagnostics.unsupported(tag, "Widget testTag requires String")
                val emitted = scalar(tag, scope)
                if (emitted.type != EtsTypes.STRING)
                    diagnostics.unsupported(tag, "Widget testTag requires target string")
                WidgetModifier.Tag(emitted, at)
            }
            "androidx.compose.foundation.clickable" -> {
                checkArguments(call, setOf("onClick", "enabled", "interactionSource", "indication"))
                for (name in listOf("interactionSource", "indication")) {
                    argument(call, name)?.let { value ->
                        diagnostics.omitUi(value, "Widget clickable $name omitted from static interaction projection",
                            "androidx.compose.foundation.clickable.$name", "omitted_animation_modifier",
                            "Click action and enabled state are preserved; press indication state and animation are omitted.")
                    }
                }
                val enabled = argument(call, "enabled")?.let {
                    if (!it.type.isBoolean()) diagnostics.unsupported(it, "Widget clickable enabled requires Boolean")
                    scalar(it, scope)
                }
                WidgetModifier.Click(event(required("onClick"), scope,
                    EtsFunctionType(emptyList(), EtsTypes.VOID), "clickable onClick"), enabled, at)
            }
            "androidx.compose.foundation.verticalScroll",
            "androidx.compose.foundation.horizontalScroll" -> {
                checkArguments(call, setOf("state", "enabled", "reverseScrolling"))
                val state = required("state")
                val resolvedState = resolve(state, scope)
                val holder = (resolvedState as? IrGetValue)?.symbol
                val binding = holder?.let(scrolls::get)
                if (binding == null) {
                    val remembered = resolvedState as? IrCall
                    if (remembered == null || symbolName(remembered.symbol.owner) !=
                        "androidx.compose.foundation.rememberScrollState") {
                        diagnostics.unsupported(state,
                            "Scroll modifier state requires rememberScrollState or source remembered ScrollState")
                    }
                    checkArguments(remembered, setOf("initial"))
                    argument(remembered, "initial")?.let { initial ->
                        val emitted = scalar(initial, scope)
                        if ((emitted as? EtsLiteral)?.value != 0) diagnostics.unsupported(initial,
                            "Native scroll currently requires a zero initial offset")
                    }
                }
                val enabled = argument(call, "enabled")?.let { value ->
                    if (!value.type.isBoolean())
                        diagnostics.unsupported(value, "Scroll modifier enabled requires Boolean")
                    scalar(value, scope)
                } ?: EtsLiteral(true, EtsTypes.BOOLEAN, at)
                argument(call, "reverseScrolling")?.let { value ->
                    if ((scalar(value, scope) as? EtsLiteral)?.value != false)
                        diagnostics.unsupported(value, "Scroll reverseScrolling requires false")
                }
                val x = EtsSymbol("compose-scroll:${at.file}:${at.start}:x", "xOffset",
                    EtsTypes.NUMBER, at)
                val y = EtsSymbol("compose-scroll:${at.file}:${at.start}:y", "yOffset",
                    EtsTypes.NUMBER, at)
                val axis = if (api.endsWith("verticalScroll")) WidgetScrollAxis.VERTICAL
                    else WidgetScrollAxis.HORIZONTAL
                val value = EtsReference(if (axis == WidgetScrollAxis.VERTICAL) y else x)
                val onScroll = binding?.let { scroll -> EtsLambda(
                    listOf(EtsParameter(x), EtsParameter(y)),
                    listOf(EtsExpressionStatement(EtsAssignment(scroll.offset, value, at))),
                    EtsTypes.VOID, at) }
                WidgetModifier.Scroll(axis, binding?.offset ?: EtsLiteral(0, EtsTypes.NUMBER, at),
                    onScroll, enabled, at)
            }
            else -> diagnostics.unsupported(call, "Unsupported resolved widget Modifier API: $api")
        }
        return previous + operation
    }

    private fun conditionalModifiers(conditional: IrWhen, scope: Scope,
        parent: WidgetLayoutScope?): List<WidgetModifier<EtsExpression, SourceSpan>> {
        val branches = conditional.branches.map { branch ->
            val condition = if (branch is IrElseBranch) null else {
                if (!branch.condition.type.isBoolean()) diagnostics.unsupported(branch.condition,
                    "Modifier condition requires Boolean")
                scalar(branch.condition, scope)
            }
            WidgetModifierBranch(condition, modifiers(branch.result, scope.fork(), parent),
                language.source(branch.result))
        }
        return listOf(WidgetModifier.Conditional(branches, language.source(conditional)))
    }

    private fun modifierLet(call: IrCall, scope: Scope,
        parent: WidgetLayoutScope?): List<WidgetModifier<EtsExpression, SourceSpan>> {
        checkArguments(call, setOf("block"))
        val receiver = call.extensionReceiver
            ?: diagnostics.unsupported(call, "Modifier let requires a receiver")
        val previous = modifiers(receiver, scope, parent)
        val blockExpression = argument(call, "block")
            ?: diagnostics.unsupported(call, "Modifier let requires a block")
        val block = lambda(blockExpression, scope)
            ?: diagnostics.unsupported(blockExpression, "Modifier let requires a direct lambda")
        val parameter = block.valueParameters.singleOrNull()
            ?: diagnostics.unsupported(block, "Modifier let requires one receiver parameter")
        val nested = scope.fork().also { it.aliases[parameter.symbol] = receiver }
        val result = when (val body = block.body) {
            is IrExpressionBody -> body.expression
            is IrBlockBody -> {
                if (body.statements.size != 1) diagnostics.unsupported(block,
                    "Modifier let supports a single expression body")
                when (val statement = body.statements.single()) {
                    is IrReturn -> statement.value
                    is IrExpression -> statement
                    else -> diagnostics.unsupported(statement, "Modifier let requires an expression result")
                }
            }
            else -> diagnostics.unsupported(block, "Modifier let requires an expression body")
        }
        val conditional = resolve(result, nested) as? IrWhen
            ?: return modifiers(result, nested, parent)
        val branches = conditional.branches.map { branch ->
            val condition = if (branch is IrElseBranch) null else {
                if (!branch.condition.type.isBoolean()) diagnostics.unsupported(branch.condition,
                    "Modifier condition requires Boolean")
                scalar(branch.condition, nested)
            }
            val branchModifiers = modifiers(branch.result, nested.fork(), parent)
            if (branchModifiers.take(previous.size) != previous) diagnostics.unsupported(branch.result,
                "Modifier let branches must extend their receiver without replacing it")
            WidgetModifierBranch(condition, branchModifiers.drop(previous.size), language.source(branch.result))
        }
        return previous + WidgetModifier.Conditional(branches, language.source(conditional))
    }

    private fun resolve(value: IrExpression, scope: Scope): IrExpression = when (value) {
        // Ordinary source vals already have a language-owned target binding and
        // must keep their single evaluation.  Alias expansion is reserved for
        // values without a target representation (Modifier/lambda/compiler
        // temporaries).
        is IrGetValue -> if (value.symbol in scope.bindings) value
            else scope.aliases[value.symbol]?.let { resolve(it, scope) } ?: value
        is IrTypeOperatorCall -> resolve(value.argument, scope)
        is IrBlock -> (value.statements.lastOrNull() as? IrExpression)?.let { resolve(it, scope) } ?: value
        is IrComposite -> (value.statements.lastOrNull() as? IrExpression)?.let { resolve(it, scope) } ?: value
        else -> value
    }

    private fun event(value: IrExpression, scope: Scope, expected: EtsFunctionType, label: String): EtsExpression {
        val resolved = resolve(value, scope)
        if (resolved !is IrFunctionExpression && resolved !is IrGetValue)
            diagnostics.unsupported(value, "Widget $label requires a lambda or bound function value")
        val emitted = language.expression(resolved, scope)
        if (emitted.type != expected)
            diagnostics.unsupported(value, "Widget $label requires $expected")
        return emitted
    }

    private fun widgetValue(value: IrExpression, scope: Scope, type: WidgetValueType): WidgetValue<EtsExpression, SourceSpan> {
        val resolved = resolve(value, scope)
        val call = resolved as? IrCall
        val owner = call?.symbol?.owner
        val property = owner?.correspondingPropertySymbol?.owner
        val propertyName = property?.let(::symbolName)
        val api = owner?.let(::symbolName)
        fun rootedInBinding(expression: IrExpression?): Boolean = when (val current = expression?.let { resolve(it, scope) }) {
            is IrGetValue -> current.symbol in scope.bindings
            is IrCall -> rootedInBinding(current.dispatchReceiver ?: current.extensionReceiver)
            is IrTypeOperatorCall -> rootedInBinding(current.argument)
            else -> false
        }
        val propertyOwner = property?.parent
        val tokenContainer = propertyOwner is IrFile ||
            (propertyOwner as? IrClass)?.kind == ClassKind.OBJECT
        val sourceOwnedToken = owner != null && property != null && sourceFile(owner) != null &&
            tokenContainer && !rootedInBinding(call.dispatchReceiver ?: call.extensionReceiver)
        val constructor = (resolved as? IrConstructorCall)?.symbol?.owner?.parent as? IrClass
        val systemFontFamily = propertyName
            ?.takeIf { it.startsWith("androidx.compose.ui.text.font.FontFamily.Companion.") }
            ?.removePrefix("androidx.compose.ui.text.font.FontFamily.Companion.")
            ?.let { name -> mapOf("Default" to "sans-serif", "SansSerif" to "sans-serif", "Serif" to "serif",
                "Monospace" to "monospace", "Cursive" to "cursive")[name] }
        val stringResource = if (api == "androidx.compose.ui.res.stringResource") {
            val id = argument(call!!, "id")?.let { resolve(it, scope) }
            (id as? IrGetField)?.symbol?.owner?.let(::symbolName) ?: api
        } else null
        val provenance = when {
            resolved is IrConst -> WidgetValueProvenance.Literal
            api == "androidx.compose.ui.graphics.Color" -> WidgetValueProvenance.Literal
            constructor != null -> WidgetValueProvenance.Literal
            propertyName == "androidx.compose.ui.unit.sp" &&
                resolve(call!!.extensionReceiver ?: call.dispatchReceiver!!, scope) is IrConst -> WidgetValueProvenance.Literal
            stringResource != null -> WidgetValueProvenance.Resource(stringResource)
            propertyName?.startsWith("androidx.compose.ui.graphics.Color.Companion.") == true ->
                WidgetValueProvenance.Resource(propertyName)
            propertyName?.startsWith("androidx.compose.ui.text.font.FontWeight.Companion.") == true ||
                propertyName?.startsWith("androidx.compose.ui.text.font.FontFamily.Companion.") == true ->
                WidgetValueProvenance.Resource(propertyName)
            sourceOwnedToken -> WidgetValueProvenance.ThemeToken(propertyName!!)
            propertyName?.startsWith("androidx.compose.material3.MaterialTheme.") == true ||
                property?.parent?.let { it as? IrClass }?.let(::symbolName) == "androidx.compose.material3.ColorScheme" ->
                WidgetValueProvenance.ThemeToken(propertyName!!)
            else -> WidgetValueProvenance.Expression((resolved as? IrGetValue)?.symbol?.owner?.name?.asString())
        }
        val expected = when (type) {
            WidgetValueType.STRING, WidgetValueType.FONT_FAMILY -> EtsTypes.STRING
            WidgetValueType.COLOR -> EtsNullableType(EtsTypes.NUMBER)
            WidgetValueType.FONT_SIZE, WidgetValueType.FONT_WEIGHT, WidgetValueType.LINE_HEIGHT -> EtsTypes.NUMBER
        }
        val emitted = if (type == WidgetValueType.FONT_FAMILY && systemFontFamily != null) {
            EtsLiteral(systemFontFamily, EtsTypes.STRING, language.source(resolved))
        } else if (sourceOwnedToken) {
            val adapted = adaptCall(call!!, language, scope, CallContext.VALUE) { expected }
            (adapted as? CallResult.Value)?.expression ?: diagnostics.unsupported(resolved,
                "Unmapped project widget token $propertyName; provide a project adapter mapping")
        } else if (provenance is WidgetValueProvenance.Expression) scalar(resolved, scope)
        else language.expression(resolved, scope)
        if (!etsAssignable(emitted.type, expected)) diagnostics.unsupported(value,
            "Widget ${type.name.lowercase()} requires target type $expected; got ${emitted.type}")
        val consumed = if (type == WidgetValueType.COLOR)
            requireSpecifiedColor(emitted, language.source(resolved), "Modifier.background") else emitted
        return WidgetValue(type, consumed, provenance, language.source(resolved))
    }

    private fun scalar(value: IrExpression, scope: Scope): EtsExpression {
        // The target tree consumes this expression exactly once at the same UI
        // position. Calls, compiler-created expression blocks and ordered effects
        // remain language-lowering concerns; resolving a block here would discard
        // the temporaries that its final expression reads.
        return language.expression(value, scope)
    }

    private fun shapeRadius(value: IrExpression, scope: Scope): EtsExpression =
        language.callRules.filterIsInstance<ComposeShapeRule>().singleOrNull()
            ?.borderRadius(value, language, scope, diagnostics)
            ?: diagnostics.unsupported(value, "Widget shape requires ComposeShapeRule")

    private fun materialInvocationContext(scope: Scope, source: SourceSpan): EtsExpression? {
        if (language.callRules.none { it is ComposeTextStyleRule } ||
            language.callRules.none { it is ComposeTypographyRule } ||
            language.callRules.none { it is ComposeMaterialThemeValueRule }) return null
        return scope.ambientValues.getOrPut(MATERIAL_CONTEXT) {
            val shapes = language.callRules.filterIsInstance<ComposeShapeRule>().singleOrNull()
                ?.initialShapes(source) ?: defaultMaterialShapes(source)
            defaultMaterialContext(source, shapes)
        }
    }

    private fun checkArguments(call: IrCall, supported: Set<String>) {
        call.symbol.owner.valueParameters.forEachIndexed { index, parameter ->
            call.getValueArgument(index)?.takeIf { parameter.name.asString() !in supported }?.let {
                diagnostics.unsupported(it, "Unsupported ${symbolName(call.symbol.owner)} widget argument: ${parameter.name}")
            }
        }
    }

    private companion object {
        val supported = setOf("androidx.compose.material.Text", "androidx.compose.material3.Text",
            "androidx.compose.material.Button", "androidx.compose.material3.Button",
            "androidx.compose.material.IconButton", "androidx.compose.material3.IconButton",
            "androidx.compose.material3.TextButton",
            "androidx.compose.foundation.Image", "coil.compose.AsyncImage",
            "androidx.compose.foundation.text.BasicTextField", "androidx.compose.material.TextField",
            "androidx.compose.material3.TextField", "androidx.compose.material3.OutlinedTextField",
            "androidx.compose.foundation.pager.HorizontalPager",
            "androidx.compose.foundation.lazy.LazyColumn", "androidx.compose.foundation.lazy.LazyRow",
            "androidx.compose.foundation.layout.Row", "androidx.compose.foundation.layout.Column",
            "androidx.compose.foundation.layout.Box", "androidx.compose.foundation.layout.Spacer")
        val lazyCollectionTypes = setOf("kotlin.Array", "kotlin.collections.List",
            "kotlin.collections.MutableList", "kotlin.IntArray", "kotlin.FloatArray",
            "kotlin.DoubleArray", "kotlin.ByteArray", "kotlin.ShortArray", "kotlin.BooleanArray")
    }
}
