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

/** Native Scroll+Column for a local rememberLazyListState and List itemsIndexed/item content. */
internal class ComposeLazyColumnRule(
    private val target: ArkUiCalls,
    private val bind: (IrValueParameter) -> EtsReference,
    private val body: (IrBody, Scope) -> List<EtsStatement>,
    decorate: (IrExpression?, Scope, ComposeElement) -> List<EtsStatement>,
) : ComposeControlRule(decorate) {
    override fun control(call: IrCall, language: Language, scope: Scope): ComposeElement? {
        if (symbolName(call.symbol.owner) != "androidx.compose.foundation.lazy.LazyColumn") return null
        target.checkArguments(call, setOf("modifier", "state", "content", "verticalArrangement", "horizontalAlignment", "userScrollEnabled"))
        validateState(argument(call, "state"), scope, call, language)
        val enabled = argument(call, "userScrollEnabled")?.let { language.expression(it, scope) } ?: target.literal(true, call)
        val children = argument(call, "content")?.let { lazyContent(it, language, scope) } ?: emptyList()
        val alignment = argument(call, "horizontalAlignment")?.let { language.expression(it, scope) }
            ?: target.enumValue("HorizontalAlign", "Start", call)
        val arrangement = argument(call, "verticalArrangement")?.let { language.expression(it, scope) }
        val options = arrangement?.let { listOf(arrangementOptions(it, "Column", target, call)) } ?: emptyList()
        val column = target.native("Column", options, call, children).copy(attributes = listOf(
            target.attribute("alignItems", listOf(alignment), call)))
        val attrs = listOf(
            target.attribute("scrollable", listOf(target.enumValue("ScrollDirection", "Vertical", call)), call),
            target.attribute("scrollBar", listOf(target.enumValue("BarState", "Off", call)), call),
            target.attribute("enableScrollInteraction", listOf(enabled), call),
            target.attribute("align", listOf(target.enumValue("Alignment", "TopStart", call)), call),
        )
        return ComposeElement(target.native("Scroll", emptyList(), call, listOf(column)).copy(attributes = attrs),
            orderedArguments = listOfNotNull(arrangement, alignment))
    }

    private fun validateState(state: IrExpression?, scope: Scope, owner: IrCall, language: Language) {
        if (state == null) return
        fun resolve(value: IrExpression?): IrExpression? =
            if (value is IrGetValue && value.symbol in scope.aliases) resolve(scope.aliases[value.symbol]) else value
        val remembered = resolve(state) as? IrCall
        if (remembered == null || symbolName(remembered.symbol.owner) != "androidx.compose.foundation.lazy.rememberLazyListState")
            target.diagnostics.unsupported(owner, "LazyColumn requires a local rememberLazyListState; shared or observed list state is not yet supported")
        target.checkArguments(remembered, setOf("initialFirstVisibleItemIndex", "initialFirstVisibleItemScrollOffset"))
        fun zero(name: String) {
            val value = argument(remembered, name)?.let { language.expression(it, scope) } ?: return
            if ((value as? EtsLiteral)?.value != 0) target.diagnostics.unsupported(remembered,
                "Native lazy list currently requires a zero $name")
        }
        zero("initialFirstVisibleItemIndex")
        zero("initialFirstVisibleItemScrollOffset")
    }

    private fun lazyContent(expression: IrExpression, language: Language, scope: Scope): List<EtsStatement> {
        val fn = lambda(expression, scope) ?: target.diagnostics.unsupported(expression, "LazyColumn requires a source content lambda")
        if (fn.valueParameters.isNotEmpty()) target.diagnostics.unsupported(fn, "LazyColumn content uses a LazyListScope receiver, not value parameters")
        return lazyBody(fn.body ?: target.diagnostics.unsupported(fn, "LazyColumn requires a content body"), language, scope.fork())
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
            else -> target.diagnostics.unsupported(call, "Unsupported LazyColumn DSL: $api")
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
