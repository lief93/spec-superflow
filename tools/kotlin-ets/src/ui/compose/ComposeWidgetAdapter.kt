@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.compose

import dev.ets.*
import dev.ets.widgets.*
import java.net.URI
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.IrStatement
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.symbols.IrValueSymbol
import org.jetbrains.kotlin.ir.types.*
import org.jetbrains.kotlin.ir.util.*
import org.jetbrains.kotlin.ir.visitors.IrElementVisitorVoid
import org.jetbrains.kotlin.ir.visitors.acceptChildrenVoid
import org.jetbrains.kotlin.ir.visitors.acceptVoid
import org.jetbrains.kotlin.name.FqName

/** Closed resolved-call adapter. No native control/attribute construction or backend dependency.
 * The caller supplies ordinary language lowering and bindings for entry parameters.
 * Children are statically described; callbacks remain typed language expressions.
 */
class ComposeWidgetAdapter(private val language: Language, private val diagnostics: DiagnosticSink,
    private val sourceWidget: ((IrCall, Scope) -> EtsExpression?)? = null,
    private val pagers: Map<IrValueSymbol, ComposeStateLowering.PagerStateBinding> = emptyMap(),
    private val scrolls: Map<IrValueSymbol, ComposeStateLowering.ScrollStateBinding> = emptyMap(),
    private val lazyLists: Map<IrValueSymbol, ComposeStateLowering.LazyListStateBinding> = emptyMap()) {
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

    fun lowerFunctionBody(function: IrFunction, scope: Scope): Children<EtsExpression, SourceSpan> =
        body(function.body ?: diagnostics.unsupported(function, "Widget helper has no body"),
            scope.fork(), function, parent = null)

    private fun body(body: IrBody, scope: Scope, owner: IrFunction,
        handledStatements: Set<IrStatement> = emptySet(), parent: WidgetLayoutScope?): Children<EtsExpression, SourceSpan> = when (body) {
        is IrBlockBody -> Children(statements(body.statements, scope, owner,
            handledStatements = handledStatements, parent = parent))
        is IrExpressionBody -> Children(statements(listOf(body.expression), scope, owner,
            handledStatements = handledStatements, parent = parent))
        else -> diagnostics.unsupported(body, "Unsupported widget body")
    }

    private fun statements(statements: List<IrStatement>, scope: Scope, owner: IrFunction, terminal: Boolean = true,
        handledStatements: Set<IrStatement> = emptySet(), parent: WidgetLayoutScope?): List<Widget<EtsExpression, SourceSpan>> =
        statements.flatMapIndexed { index, statement -> if (statement in handledStatements) emptyList() else when (statement) {
            is IrVariable -> {
                val initial = statement.initializer ?: diagnostics.unsupported(statement, "Uninitialized widget local")
                if (statement.isVar) diagnostics.unsupported(statement, "Mutable widget local is outside the static widget subset")
                when {
                    initial.type.classFqName?.asString() in setOf("androidx.compose.ui.Modifier", "androidx.compose.ui.Modifier.Companion") ->
                        modifiers(initial, scope, parent)
                    resolve(initial, scope) is IrFunctionExpression -> Unit
                    else -> scalar(initial, scope)
                }
                scope.aliases[statement.symbol] = initial
                emptyList()
            }
            is IrCall -> listOf(widget(statement, scope, parent))
            is IrWhen -> listOf(conditional(statement, scope, owner, parent))
            is IrBlock -> statements(statement.statements, scope.fork(), owner, terminal && index == statements.lastIndex,
                handledStatements, parent)
            is IrReturn -> {
                if (statement.returnTargetSymbol.owner !== owner || !terminal || index != statements.lastIndex)
                    diagnostics.unsupported(statement, "Widget return must terminate its own children body")
                statements(listOf(statement.value), scope, owner,
                    handledStatements = handledStatements, parent = parent)
            }
            is IrGetObjectValue -> if (statement.type.isUnit()) emptyList() else
                diagnostics.unsupported(statement, "Unsupported object in widget children")
            else -> diagnostics.unsupported(statement, "Unsupported widget children statement: ${statement.javaClass.simpleName}")
        } }

    private fun conditional(value: IrWhen, scope: Scope, owner: IrFunction,
        parent: WidgetLayoutScope?): Widget.Conditional<EtsExpression, SourceSpan> {
        if (!value.type.isUnit()) diagnostics.unsupported(value, "Widget conditional must produce Unit children")
        val branches = value.branches.map { branch ->
            val condition = if (branch is IrElseBranch) null else {
                if (!branch.condition.type.isBoolean())
                    diagnostics.unsupported(branch.condition, "Widget conditional requires a Boolean condition")
                scalar(branch.condition, scope)
            }
            val nested = scope.fork()
            val children = Children(statements(listOf(branch.result), nested, owner, parent = parent))
            WidgetBranch(condition, children, language.source(branch.result))
        }
        return Widget.Conditional(branches, language.source(value))
    }

    private fun widget(call: IrCall, scope: Scope, parent: WidgetLayoutScope?): Widget<EtsExpression, SourceSpan> {
        sourceWidget?.invoke(call, scope)?.let { lowered ->
            if (lowered.type != EtsTypes.VOID)
                diagnostics.unsupported(call, "Source composable call must produce target void")
            return Widget.BuilderCall(lowered, language.source(call))
        }
        val api = symbolName(call.symbol.owner)
        if (sourceFile(call.symbol.owner) != null || !call.type.isUnit() || api !in supported)
            diagnostics.unsupported(call, "Unsupported resolved widget API: $api")
        val text = api.endsWith(".Text")
        val button = api.endsWith(".Button")
        val image = api in setOf("androidx.compose.foundation.Image", "coil.compose.AsyncImage")
        val textField = api.endsWith("TextField")
        val isPager = api == "androidx.compose.foundation.pager.HorizontalPager"
        val isLazyList = api in setOf("androidx.compose.foundation.lazy.LazyColumn",
            "androidx.compose.foundation.lazy.LazyRow")
        checkArguments(call, when {
            text -> setOf("text", "modifier", "fontSize", "fontWeight", "fontFamily", "lineHeight")
            button -> setOf("onClick", "enabled", "modifier", "content")
            image -> if (api == "androidx.compose.foundation.Image")
                setOf("painter", "contentDescription", "modifier")
            else setOf("model", "contentDescription", "modifier")
            textField -> setOf("value", "onValueChange", "modifier", "enabled")
            isPager -> setOf("state", "modifier", "pageContent")
            isLazyList -> setOf("modifier", "state", "content", "userScrollEnabled")
            else -> setOf("modifier", "content")
        })
        val source = language.source(call)
        val modifier = modifiers(argument(call, "modifier"), scope, parent)
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
            val style = WidgetTextStyle(
                style("fontSize", "androidx.compose.ui.unit.TextUnit", WidgetValueType.FONT_SIZE),
                style("fontWeight", "androidx.compose.ui.text.font.FontWeight", WidgetValueType.FONT_WEIGHT),
                style("fontFamily", "androidx.compose.ui.text.font.FontFamily", WidgetValueType.FONT_FAMILY),
                style("lineHeight", "androidx.compose.ui.unit.TextUnit", WidgetValueType.LINE_HEIGHT))
            return Widget.Text(widgetValue(value, scope, WidgetValueType.STRING), style, modifier, source)
        }
        if (image) return image(call, api, scope, modifier, source)
        if (isPager) return pager(call, scope, modifier, source)
        if (isLazyList) return lazyList(call, api, scope, modifier, source)
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
        val children = if (content == null && api == "androidx.compose.foundation.layout.Box" &&
            call.symbol.owner.valueParameters.none { it.name.asString() == "content" }) Children(emptyList()) else {
            val value = content ?: diagnostics.unsupported(call, "$api requires content")
            val lambda = resolve(value, scope) as? IrFunctionExpression
                ?: diagnostics.unsupported(value, "Widget children require a statically resolved lambda")
            val childParent = when {
                button || api.endsWith(".Row") -> WidgetLayoutScope.ROW
                api.endsWith(".Column") -> WidgetLayoutScope.COLUMN
                else -> WidgetLayoutScope.BOX
            }
            body(lambda.function.body ?: diagnostics.unsupported(value, "Widget children have no body"),
                scope.fork(), lambda.function, parent = childParent)
        }
        return when {
            button -> Widget.Button(event(required("onClick"), scope,
                EtsFunctionType(emptyList(), EtsTypes.VOID), "callback"), argument(call, "enabled")?.let {
                if (!it.type.isBoolean()) diagnostics.unsupported(it, "Widget Button enabled requires Boolean")
                scalar(it, scope)
            }, children, modifier, source)
            api.endsWith(".Row") -> Widget.Row(children, modifier, source)
            api.endsWith(".Column") -> Widget.Column(children, modifier, source)
            else -> Widget.Box(children, modifier, source)
        }
    }

    private fun pager(call: IrCall, scope: Scope,
        modifiers: List<WidgetModifier<EtsExpression, SourceSpan>>,
        source: SourceSpan): Widget.Pager<EtsExpression, SourceSpan> {
        val state = argument(call, "state")
            ?: diagnostics.unsupported(call, "HorizontalPager requires state")
        val holder = (resolve(state, scope) as? IrGetValue)?.symbol
        val binding = holder?.let(pagers::get)
            ?: diagnostics.unsupported(state, "HorizontalPager state requires source remembered PagerState")
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
        return Widget.Pager(binding.currentPage, binding.pageCount, binding.controller, onPageChange,
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
        if (expression is IrGetObjectValue && sourceFile(expression.symbol.owner) == null &&
            symbolName(expression.symbol.owner) == "androidx.compose.ui.Modifier.Companion") return emptyList()
        val call = expression as? IrCall ?: diagnostics.unsupported(expression, "Unsupported widget Modifier value")
        if (sourceFile(call.symbol.owner) != null) diagnostics.unsupported(call, "Source Modifier functions require explicit widget semantics")
        val api = symbolName(call.symbol.owner)
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
        val operation = when (api) {
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
                checkArguments(call, setOf("all", "horizontal", "vertical", "start", "top", "end", "bottom"))
                // Reject the PaddingValues overload even when its explicit value is absent.
                if (call.symbol.owner.valueParameters.any { it.name.asString() == "paddingValues" })
                    diagnostics.unsupported(call, "PaddingValues is outside the widget subset")
                fun side(name: String, axis: String) = (argument(call, "all") ?: argument(call, name) ?: argument(call, axis))
                    ?.let(::dimension) ?: EtsLiteral(0, EtsTypes.NUMBER, at)
                WidgetModifier.Padding(side("start", "horizontal"), side("top", "vertical"),
                    side("end", "horizontal"), side("bottom", "vertical"), at)
            }
            "androidx.compose.foundation.background" -> {
                checkArguments(call, setOf("color"))
                val color = required("color")
                WidgetModifier.Background(widgetValue(color, scope, WidgetValueType.COLOR), at)
            }
            "androidx.compose.foundation.clickable" -> {
                checkArguments(call, setOf("onClick", "enabled"))
                val enabled = argument(call, "enabled")?.let {
                    if (!it.type.isBoolean()) diagnostics.unsupported(it, "Widget clickable enabled requires Boolean")
                    scalar(it, scope)
                }
                WidgetModifier.Click(event(required("onClick"), scope,
                    EtsFunctionType(emptyList(), EtsTypes.VOID), "clickable onClick"), enabled, at)
            }
            "androidx.compose.foundation.verticalScroll",
            "androidx.compose.foundation.horizontalScroll" -> {
                checkArguments(call, setOf("state", "enabled"))
                val state = required("state")
                val holder = (resolve(state, scope) as? IrGetValue)?.symbol
                val binding = holder?.let(scrolls::get)
                    ?: diagnostics.unsupported(state,
                        "Scroll modifier state requires source remembered ScrollState")
                val enabled = argument(call, "enabled")?.let { value ->
                    if (!value.type.isBoolean())
                        diagnostics.unsupported(value, "Scroll modifier enabled requires Boolean")
                    scalar(value, scope)
                } ?: EtsLiteral(true, EtsTypes.BOOLEAN, at)
                val x = EtsSymbol("compose-scroll:${at.file}:${at.start}:x", "xOffset",
                    EtsTypes.NUMBER, at)
                val y = EtsSymbol("compose-scroll:${at.file}:${at.start}:y", "yOffset",
                    EtsTypes.NUMBER, at)
                val axis = if (api.endsWith("verticalScroll")) WidgetScrollAxis.VERTICAL
                    else WidgetScrollAxis.HORIZONTAL
                val value = EtsReference(if (axis == WidgetScrollAxis.VERTICAL) y else x)
                val onScroll = EtsLambda(listOf(EtsParameter(x), EtsParameter(y)),
                    listOf(EtsExpressionStatement(EtsAssignment(binding.offset, value, at))),
                    EtsTypes.VOID, at)
                WidgetModifier.Scroll(axis, binding.offset, onScroll, enabled, at)
            }
            else -> diagnostics.unsupported(call, "Unsupported resolved widget Modifier API: $api")
        }
        return previous + operation
    }

    private fun resolve(value: IrExpression, scope: Scope): IrExpression = when (value) {
        is IrGetValue -> scope.aliases[value.symbol]?.let { resolve(it, scope) } ?: value
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
        val sourceOwnedToken = owner != null && property != null && sourceFile(owner) != null &&
            !rootedInBinding(call.dispatchReceiver ?: call.extensionReceiver)
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
        val emitted = language.expression(resolve(value, scope), scope)
        fun stable(expression: EtsExpression): Boolean = when (expression) {
            is EtsLiteral, is EtsReference -> true
            is EtsMember -> expression.symbolId != null && stable(expression.receiver)
            is EtsCast -> stable(expression.value)
            is EtsBinary -> stable(expression.left) && stable(expression.right)
            is EtsUnary -> stable(expression.operand)
            is EtsConditional -> stable(expression.condition) && stable(expression.whenTrue) && stable(expression.whenFalse)
            is EtsCall -> (expression.callee as? EtsMember)?.let { member ->
                member.name == "fround" && (member.receiver as? EtsReference)?.symbol?.id == "stdlib:Math" &&
                    expression.arguments.all(::stable)
            } == true
            else -> false
        }
        if (!stable(emitted)) diagnostics.unsupported(value,
            "Widget values require stable scalars; effectful evaluation is outside this subset")
        return emitted
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
            "androidx.compose.foundation.Image", "coil.compose.AsyncImage",
            "androidx.compose.foundation.text.BasicTextField", "androidx.compose.material.TextField",
            "androidx.compose.material3.TextField", "androidx.compose.material3.OutlinedTextField",
            "androidx.compose.foundation.pager.HorizontalPager",
            "androidx.compose.foundation.lazy.LazyColumn", "androidx.compose.foundation.lazy.LazyRow",
            "androidx.compose.foundation.layout.Row", "androidx.compose.foundation.layout.Column",
            "androidx.compose.foundation.layout.Box")
        val lazyCollectionTypes = setOf("kotlin.Array", "kotlin.collections.List",
            "kotlin.collections.MutableList", "kotlin.IntArray", "kotlin.FloatArray",
            "kotlin.DoubleArray", "kotlin.ByteArray", "kotlin.ShortArray", "kotlin.BooleanArray")
    }
}
