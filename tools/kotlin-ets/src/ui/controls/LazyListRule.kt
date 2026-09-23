@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.IrStatement
import org.jetbrains.kotlin.ir.declarations.IrFunction
import org.jetbrains.kotlin.ir.declarations.IrValueParameter
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.classOrNull
import org.jetbrains.kotlin.ir.types.isUnit
import org.jetbrains.kotlin.ir.visitors.IrElementVisitorVoid
import org.jetbrains.kotlin.ir.visitors.acceptChildrenVoid
import org.jetbrains.kotlin.ir.visitors.acceptVoid

/** Native scrolling Row/Column for LazyList item, items and itemsIndexed content. */
internal class ComposeLazyListRule(
    private val target: ArkUiCalls,
    private val bind: (IrValueParameter) -> EtsReference,
    private val body: (IrBody, Scope) -> List<EtsStatement>,
    private val indexItems: (EtsExpression, IrElement) -> EtsExpression,
    decorate: (IrExpression?, Scope, ComposeElement) -> List<EtsStatement>,
) : ComposeControlRule(decorate) {
    override fun control(call: IrCall, language: Language, scope: Scope): ComposeElement? {
        val api = symbolName(call.symbol.owner)
        if (api !in setOf("androidx.compose.foundation.lazy.LazyColumn",
                "androidx.compose.foundation.lazy.LazyRow")) return null
        val vertical = api.endsWith("LazyColumn")
        target.checkArguments(call, setOf("modifier", "state", "content", "verticalArrangement",
            "horizontalArrangement", "horizontalAlignment", "verticalAlignment", "userScrollEnabled"))
        validateState(argument(call, "state"), scope, call, language, api.substringAfterLast('.'))
        val enabled = argument(call, "userScrollEnabled")?.let { language.expression(it, scope) } ?: target.literal(true, call)
        val children = argument(call, "content")?.let { lazyContent(it, language, scope, api) } ?: emptyList()
        val alignment = argument(call, if (vertical) "horizontalAlignment" else "verticalAlignment")
            ?.let { language.expression(it, scope) }
            ?: target.enumValue(if (vertical) "HorizontalAlign" else "VerticalAlign",
                if (vertical) "Start" else "Center", call)
        val arrangementSource = argument(call, if (vertical) "verticalArrangement" else "horizontalArrangement")
        val justification = arrangementSource?.let { arrangementAlignment(it, scope, target) }
        val arrangement = arrangementSource?.takeIf { justification == null }?.let { language.expression(it, scope) }
        val container = if (vertical) "Column" else "Row"
        val options = arrangement?.let { listOf(arrangementOptions(it, container, target, call)) } ?: emptyList()
        val content = target.native(container, options, call, children).copy(attributes = listOf(
            target.attribute("alignItems", listOf(alignment), call)) + listOfNotNull(
            justification?.let { target.attribute("justifyContent", listOf(it), call) }))
        val attrs = listOf(
            target.attribute("scrollable", listOf(target.enumValue("ScrollDirection",
                if (vertical) "Vertical" else "Horizontal", call)), call),
            target.attribute("scrollBar", listOf(target.enumValue("BarState", "Off", call)), call),
            target.attribute("enableScrollInteraction", listOf(enabled), call),
            target.attribute("align", listOf(target.enumValue("Alignment", "TopStart", call)), call),
        )
        return ComposeElement(target.native("Scroll", emptyList(), call, listOf(content)).copy(attributes = attrs),
            orderedArguments = listOfNotNull(arrangement, justification, alignment))
    }

    private fun validateState(state: IrExpression?, scope: Scope, owner: IrCall, language: Language,
        control: String) {
        if (state == null) return
        fun resolve(value: IrExpression?): IrExpression? =
            if (value is IrGetValue && value.symbol in scope.aliases) resolve(scope.aliases[value.symbol]) else value
        val remembered = resolve(state) as? IrCall
        if (remembered == null || symbolName(remembered.symbol.owner) != "androidx.compose.foundation.lazy.rememberLazyListState")
            target.diagnostics.unsupported(owner,
                "$control requires a local rememberLazyListState; shared or observed list state is not yet supported")
        target.checkArguments(remembered, setOf("initialFirstVisibleItemIndex", "initialFirstVisibleItemScrollOffset"))
        fun zero(name: String) {
            val value = argument(remembered, name)?.let { language.expression(it, scope) } ?: return
            if ((value as? EtsLiteral)?.value != 0) target.diagnostics.unsupported(remembered,
                "Native lazy list currently requires a zero $name")
        }
        zero("initialFirstVisibleItemIndex")
        zero("initialFirstVisibleItemScrollOffset")
    }

    private fun lazyContent(expression: IrExpression, language: Language, scope: Scope,
        api: String): List<EtsStatement> {
        val control = api.substringAfterLast('.')
        val fn = lambda(expression, scope)
            ?: target.diagnostics.unsupported(expression, "$control requires a source content lambda")
        if (fn.valueParameters.isNotEmpty()) target.diagnostics.unsupported(fn,
            "$control content uses a LazyListScope receiver, not value parameters")
        return lazyBody(fn.body ?: target.diagnostics.unsupported(fn, "$control requires a content body"),
            language, scope.fork())
    }

    private fun lazyBody(body: IrBody, language: Language, scope: Scope): List<EtsStatement> = when (body) {
        is IrBlockBody -> body.statements.flatMap { lazyStatement(it, language, scope) }
        is IrExpressionBody -> lazyStatement(body.expression, language, scope)
        else -> target.diagnostics.unsupported(body, "Unsupported LazyColumn content body")
    }

    private fun lazyStatement(node: IrStatement, language: Language, scope: Scope): List<EtsStatement> = when (node) {
        is IrReturn -> lazyStatement(node.value, language, scope)
        is IrBlock -> node.statements.flatMap { lazyStatement(it, language, scope.fork()) }
        is IrComposite -> node.statements.flatMap { lazyStatement(it, language, scope) }
        is IrGetObjectValue -> if (node.type.isUnit()) emptyList() else target.diagnostics.unsupported(node, "Unexpected LazyColumn value")
        is IrWhen -> listOf(EtsIf(node.branches.map { branch -> EtsBranch(
            if (branch is IrElseBranch) null else language.expression(branch.condition, scope),
            lazyStatement(branch.result, language, scope.fork())) }, language.source(node)))
        is IrCall -> lazyCall(node, language, scope)
        else -> target.diagnostics.unsupported(node, "Unsupported LazyColumn statement ${node::class.simpleName}")
    }

    private fun lazyCall(call: IrCall, language: Language, scope: Scope): List<EtsStatement> {
        val api = symbolName(call.symbol.owner)
        return when (api) {
            "androidx.compose.foundation.lazy.items",
            "androidx.compose.foundation.lazy.LazyListScope.items" -> {
                target.checkArguments(call, setOf("items", "count", "itemContent"))
                val items = argument(call, "items")
                val count = argument(call, "count")
                if ((items == null) == (count == null))
                    target.diagnostics.unsupported(call, "items requires exactly one list or count source")
                val fn = contentLambda(argument(call, "itemContent"), scope, call)
                val parameter = fn.valueParameters.singleOrNull()
                    ?: target.diagnostics.unsupported(fn, "items requires one item or index parameter")
                if (fn.extensionReceiverParameter != null && used(fn.extensionReceiverParameter!!, fn.body ?: fn))
                    target.diagnostics.unsupported(fn, "LazyItemScope members are not mapped")
                val child = scope.fork()
                val value = bind(parameter)
                child.bindings[parameter.symbol] = value
                val values = if (items != null) {
                    if (items.type.classOrNull?.owner?.let(::symbolName) !in
                        setOf("kotlin.collections.List", "kotlin.collections.MutableList"))
                        target.diagnostics.unsupported(items, "items currently requires a List or count")
                    language.expression(items, scope)
                } else indexItems(language.expression(checkNotNull(count), scope), call)
                listOf(EtsUiForEach(values, EtsParameter(value.symbol),
                    body(fn.body ?: target.diagnostics.unsupported(call, "items requires a body"), child),
                    language.source(call)))
            }
            "androidx.compose.foundation.lazy.itemsIndexed",
            "androidx.compose.foundation.lazy.LazyListScope.itemsIndexed" -> {
                target.checkArguments(call, setOf("items", "itemContent"))
                val items = argument(call, "items") ?: target.diagnostics.unsupported(call, "itemsIndexed requires items")
                if (items.type.classOrNull?.owner?.let(::symbolName) !in setOf("kotlin.collections.List", "kotlin.collections.MutableList"))
                    target.diagnostics.unsupported(items, "itemsIndexed currently requires a List")
                val fn = contentLambda(argument(call, "itemContent"), scope, call)
                val index = fn.valueParameters.getOrNull(0) ?: target.diagnostics.unsupported(fn, "itemsIndexed requires index and item parameters")
                val item = fn.valueParameters.getOrNull(1) ?: target.diagnostics.unsupported(fn, "itemsIndexed requires index and item parameters")
                if (fn.valueParameters.size != 2) target.diagnostics.unsupported(fn, "itemsIndexed requires index and item parameters")
                if (used(index, fn.body ?: fn)) target.diagnostics.unsupported(index,
                    "itemsIndexed currently ignores the source index; use the item value only")
                if (fn.extensionReceiverParameter != null && used(fn.extensionReceiverParameter!!, fn.body ?: fn))
                    target.diagnostics.unsupported(fn, "LazyItemScope members are not mapped")
                val child = scope.fork()
                val value = bind(item)
                child.bindings[item.symbol] = value
                listOf(EtsUiForEach(language.expression(items, scope), EtsParameter(value.symbol),
                    body(fn.body ?: target.diagnostics.unsupported(call, "itemsIndexed requires a body"), child), language.source(call)))
            }
            "androidx.compose.foundation.lazy.LazyListScope.item", "androidx.compose.foundation.lazy.item" -> {
                target.checkArguments(call, setOf("content"))
                val fn = contentLambda(argument(call, "content"), scope, call)
                if (fn.valueParameters.isNotEmpty()) target.diagnostics.unsupported(fn, "item content currently requires no value parameters")
                if (fn.extensionReceiverParameter != null && used(fn.extensionReceiverParameter!!, fn.body ?: fn))
                    target.diagnostics.unsupported(fn, "LazyItemScope members are not mapped")
                body(fn.body ?: target.diagnostics.unsupported(call, "item requires a body"), scope.fork())
            }
            else -> target.diagnostics.unsupported(call, "Unsupported lazy list DSL: $api")
        }
    }

    private fun contentLambda(expression: IrExpression?, scope: Scope, owner: IrElement): IrFunction =
        lambda(expression, scope) ?: target.diagnostics.unsupported(owner, "Expected source lazy item lambda")

    private fun used(parameter: IrValueParameter, element: IrElement): Boolean {
        var found = false
        element.acceptVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) { if (!found) element.acceptChildrenVoid(this) }
            override fun visitGetValue(expression: IrGetValue) {
                if (expression.symbol == parameter.symbol) found = true
                if (!found) expression.acceptChildrenVoid(this)
            }
        })
        return found
    }
}

/** Native Grid/GridItem lowering for finite vertical lazy grids backed by List values. */
internal class ComposeLazyVerticalGridRule(
    private val target: ArkUiCalls,
    private val bind: (IrValueParameter) -> EtsReference,
    private val body: (IrBody, Scope) -> List<EtsStatement>,
    private val dimension: (IrExpression, Scope) -> EtsExpression,
    decorate: (IrExpression?, Scope, ComposeElement) -> List<EtsStatement>,
) : ComposeControlRule(decorate) {
    override fun control(call: IrCall, language: Language, scope: Scope): ComposeElement? {
        if (symbolName(call.symbol.owner) != "androidx.compose.foundation.lazy.grid.LazyVerticalGrid") return null
        target.checkArguments(call, setOf("columns", "modifier", "state", "contentPadding", "content", "userScrollEnabled"))
        argument(call, "state")?.let {
            target.diagnostics.unsupported(it, "LazyVerticalGrid state and scroll restoration are not yet supported")
        }
        val columns = argument(call, "columns")
            ?: target.diagnostics.unsupported(call, "LazyVerticalGrid requires columns")
        val attributes = gridCells(columns, language, scope).toMutableList()
        val ordered = attributes.flatMap { it.arguments }.toMutableList()
        argument(call, "contentPadding")?.let {
            val padding = language.expression(it, scope)
            attributes += target.attribute("padding", listOf(padding), call)
            ordered += padding
        }
        val enabled = argument(call, "userScrollEnabled")?.let { language.expression(it, scope) }
            ?: target.literal(true, call)
        ordered += enabled
        attributes += target.attribute("enableScrollInteraction", listOf(enabled), call)
        attributes += target.attribute("scrollBar", listOf(target.enumValue("BarState", "Off", call)), call)
        val children = argument(call, "content")?.let { lazyContent(it, language, scope) }
            ?: target.diagnostics.unsupported(call, "LazyVerticalGrid requires content")
        return ComposeElement(target.native("Grid", emptyList(), call, children).copy(attributes = attributes),
            orderedArguments = ordered)
    }

    private fun gridCells(expression: IrExpression, language: Language, scope: Scope): List<EtsCall> {
        val call = resolveExpression(expression, scope) as? IrConstructorCall
            ?: target.diagnostics.unsupported(expression, "LazyVerticalGrid columns require GridCells.Fixed or GridCells.Adaptive")
        val owner = call.symbol.owner.parent as? org.jetbrains.kotlin.ir.declarations.IrClass
            ?: target.diagnostics.unsupported(call, "LazyVerticalGrid columns require a GridCells constructor")
        return when (symbolName(owner)) {
            "androidx.compose.foundation.lazy.grid.GridCells.Fixed" -> {
                val countSource = argument(call, "count")
                    ?: target.diagnostics.unsupported(call, "GridCells.Fixed requires count")
                val count = language.expression(countSource, scope)
                val literal = (count as? EtsLiteral)?.value as? Number
                    ?: target.diagnostics.unsupported(countSource, "GridCells.Fixed count must be statically resolved")
                val value = literal.toInt()
                if (literal.toDouble() != value.toDouble() || value <= 0)
                    target.diagnostics.unsupported(countSource, "GridCells.Fixed count must be a positive integer")
                listOf(target.attribute("columnsTemplate",
                    listOf(target.literal(List(value) { "1fr" }.joinToString(" "), call)), call))
            }
            "androidx.compose.foundation.lazy.grid.GridCells.Adaptive" -> {
                val minSize = argument(call, "minSize")
                    ?: target.diagnostics.unsupported(call, "GridCells.Adaptive requires minSize")
                listOf(
                    target.attribute("cellLength", listOf(dimension(minSize, scope)), call),
                    target.attribute("minCount", listOf(target.literal(1, call)), call),
                )
            }
            else -> target.diagnostics.unsupported(call,
                "LazyVerticalGrid columns require GridCells.Fixed or GridCells.Adaptive")
        }
    }

    private fun lazyContent(expression: IrExpression, language: Language, scope: Scope): List<EtsStatement> {
        val fn = lambda(expression, scope)
            ?: target.diagnostics.unsupported(expression, "LazyVerticalGrid requires a source content lambda")
        if (fn.valueParameters.isNotEmpty())
            target.diagnostics.unsupported(fn, "LazyVerticalGrid content uses a LazyGridScope receiver, not value parameters")
        return lazyBody(fn.body ?: target.diagnostics.unsupported(fn, "LazyVerticalGrid requires a content body"),
            language, scope.fork())
    }

    private fun lazyBody(value: IrBody, language: Language, scope: Scope): List<EtsStatement> = when (value) {
        is IrBlockBody -> value.statements.flatMap { lazyStatement(it, language, scope) }
        is IrExpressionBody -> lazyStatement(value.expression, language, scope)
        else -> target.diagnostics.unsupported(value, "Unsupported LazyVerticalGrid content body")
    }

    private fun lazyStatement(node: IrStatement, language: Language, scope: Scope): List<EtsStatement> = when (node) {
        is IrReturn -> lazyStatement(node.value, language, scope)
        is IrBlock -> node.statements.flatMap { lazyStatement(it, language, scope.fork()) }
        is IrComposite -> node.statements.flatMap { lazyStatement(it, language, scope) }
        is IrGetObjectValue -> if (node.type.isUnit()) emptyList() else
            target.diagnostics.unsupported(node, "Unexpected LazyVerticalGrid value")
        is IrWhen -> listOf(EtsIf(node.branches.map { branch -> EtsBranch(
            if (branch is IrElseBranch) null else language.expression(branch.condition, scope),
            lazyStatement(branch.result, language, scope.fork())) }, language.source(node)))
        is IrCall -> lazyCall(node, language, scope)
        else -> target.diagnostics.unsupported(node,
            "Unsupported LazyVerticalGrid statement ${node::class.simpleName}")
    }

    private fun lazyCall(call: IrCall, language: Language, scope: Scope): List<EtsStatement> {
        val api = symbolName(call.symbol.owner)
        if (api in setOf("androidx.compose.foundation.lazy.grid.LazyGridScope.item",
                "androidx.compose.foundation.lazy.grid.item")) {
            target.checkArguments(call, setOf("content"))
            val fn = contentLambda(argument(call, "content"), scope, call)
            if (fn.valueParameters.isNotEmpty())
                target.diagnostics.unsupported(fn, "LazyVerticalGrid item content requires no value parameters")
            rejectReceiverUse(fn)
            return listOf(gridItem(body(fn.body
                ?: target.diagnostics.unsupported(call, "LazyVerticalGrid item requires a body"), scope.fork()), call))
        }
        if (api !in setOf("androidx.compose.foundation.lazy.grid.items",
                "androidx.compose.foundation.lazy.grid.LazyGridScope.items"))
            target.diagnostics.unsupported(call, "Unsupported LazyVerticalGrid DSL: $api")
        target.checkArguments(call, setOf("items", "key", "itemContent"))
        val items = argument(call, "items")
            ?: target.diagnostics.unsupported(call, "LazyVerticalGrid items requires a List")
        if (items.type.classOrNull?.owner?.let(::symbolName) !in
            setOf("kotlin.collections.List", "kotlin.collections.MutableList"))
            target.diagnostics.unsupported(items, "LazyVerticalGrid items currently requires a List")
        val loweredItems = language.expression(items, scope)
        val fn = contentLambda(argument(call, "itemContent"), scope, call)
        val item = fn.valueParameters.singleOrNull()
            ?: target.diagnostics.unsupported(fn, "LazyVerticalGrid itemContent requires one item parameter")
        rejectReceiverUse(fn)
        val child = scope.fork()
        val value = bind(item)
        child.bindings[item.symbol] = value
        val contents = body(fn.body
            ?: target.diagnostics.unsupported(call, "LazyVerticalGrid itemContent requires a body"), child)
        val key = argument(call, "key")?.let { keyExpression ->
            val keyFunction = contentLambda(keyExpression, scope, call)
            val keyParameter = keyFunction.valueParameters.singleOrNull()
                ?: target.diagnostics.unsupported(keyFunction, "LazyVerticalGrid key requires one item parameter")
            val keyScope = scope.fork()
            keyScope.bindings[keyParameter.symbol] = value
            var emitted = language.expression(lambdaResult(keyFunction), keyScope)
            if (emitted.type == EtsTypes.NUMBER) emitted = EtsCall(EtsMember(emitted, "toString",
                EtsFunctionType(emptyList(), EtsTypes.STRING), language.source(keyFunction)), emptyList(),
                EtsTypes.STRING, language.source(keyFunction))
            if (emitted.type != EtsTypes.STRING)
                target.diagnostics.unsupported(keyExpression, "LazyVerticalGrid key requires a stable String or Int value")
            EtsLambda(listOf(EtsParameter(value.symbol)), listOf(EtsReturn(emitted, language.source(keyFunction))),
                EtsTypes.STRING, language.source(keyFunction))
        }
        return listOf(EtsUiForEach(loweredItems, EtsParameter(value.symbol), listOf(gridItem(contents, call)),
            language.source(call), key))
    }

    private fun gridItem(children: List<EtsStatement>, owner: IrElement): EtsUiElement {
        if (children.size != 1)
            target.diagnostics.unsupported(owner, "LazyVerticalGrid items require exactly one root UI element")
        return target.native("GridItem", emptyList(), owner, children)
    }

    private fun contentLambda(expression: IrExpression?, scope: Scope, owner: IrElement): IrFunction =
        lambda(expression, scope) ?: target.diagnostics.unsupported(owner, "Expected source lazy grid item lambda")

    private fun lambdaResult(function: IrFunction): IrExpression {
        val value = when (val value = function.body) {
            is IrExpressionBody -> value.expression
            is IrBlockBody -> (value.statements.singleOrNull() as? IrReturn)?.takeIf {
                it.returnTargetSymbol.owner === function
            }?.value
            else -> null
        }
        return value ?: target.diagnostics.unsupported(function,
            "LazyVerticalGrid key requires a single expression result")
    }

    private fun rejectReceiverUse(function: IrFunction) {
        function.extensionReceiverParameter?.let { receiver ->
            if (used(receiver, function.body ?: function))
                target.diagnostics.unsupported(receiver, "LazyGridItemScope members are not mapped")
        }
    }

    private fun used(parameter: IrValueParameter, element: IrElement): Boolean {
        var found = false
        element.acceptVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) { if (!found) element.acceptChildrenVoid(this) }
            override fun visitGetValue(expression: IrGetValue) {
                if (expression.symbol == parameter.symbol) found = true
                if (!found) expression.acceptChildrenVoid(this)
            }
        })
        return found
    }
}

internal fun validateRememberLazyListState(call: IrCall, language: Language, scope: Scope, diagnostics: DiagnosticSink) {
    if (symbolName(call.symbol.owner) != "androidx.compose.foundation.lazy.rememberLazyListState") return
    val target = ArkUiCalls(language, diagnostics)
    target.checkArguments(call, setOf("initialFirstVisibleItemIndex", "initialFirstVisibleItemScrollOffset"))
    fun zero(name: String) {
        val value = argument(call, name)?.let { language.expression(it, scope) } ?: return
        if ((value as? EtsLiteral)?.value != 0) diagnostics.unsupported(call, "Native lazy list currently requires a zero $name")
    }
    zero("initialFirstVisibleItemIndex")
    zero("initialFirstVisibleItemScrollOffset")
}
