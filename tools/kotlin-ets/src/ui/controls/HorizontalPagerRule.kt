@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.declarations.IrValueDeclaration
import org.jetbrains.kotlin.ir.expressions.*

internal data class ComposePagerBinding(val count: EtsExpression, val current: EtsMember, val controller: EtsExpression)

internal class ComposeHorizontalPagerRule(
    private val target: ArkUiCalls,
    private val state: (IrCall, Scope) -> ComposePagerBinding,
    private val binding: (IrValueDeclaration) -> EtsReference,
    private val body: (IrBody, Scope) -> List<EtsStatement>,
    private val contentFlags: (IrExpression?, Scope) -> Set<String>,
    private val indexItems: (EtsExpression, IrElement) -> EtsExpression,
    decorate: (IrExpression?, Scope, ComposeElement) -> List<EtsStatement>,
) : ComposeControlRule(decorate) {
    override fun control(call: IrCall, language: Language, scope: Scope): ComposeElement? {
        if (symbolName(call.symbol.owner) != "androidx.compose.foundation.pager.HorizontalPager") return null
        target.checkArguments(call, setOf("state", "modifier", "pageContent", "userScrollEnabled",
            "flingBehavior", "snapPosition"))
        validatePagerBehavior(call, scope, target.diagnostics)
        val pager = state(call, scope)
        val enabled = argument(call, "userScrollEnabled")?.let { language.expression(it, scope) }
            ?: target.literal(true, call)
        val fn = lambda(argument(call, "pageContent"), scope) ?: target.diagnostics.unsupported(call, "Pager requires page content")
        val parameter = fn.valueParameters.singleOrNull() ?: target.diagnostics.unsupported(fn, "Pager content requires page index")
        val child = scope.fork()
        child.semanticFlags.removeAll(setOf(UNBOUNDED_WIDTH, UNBOUNDED_HEIGHT))
        child.semanticFlags += contentFlags(argument(call, "modifier"), scope)
        child.bindings[parameter.symbol] = binding(parameter)
        val source = language.source(call)
        val index = EtsSymbol("ui:pager:${call.startOffset}", "index", EtsTypes.NUMBER, source)
        val onChange = EtsLambda(listOf(EtsParameter(index)), listOf(EtsExpressionStatement(
            EtsAssignment(pager.current, EtsReference(index), source))), EtsTypes.VOID, source)
        return ComposeElement(target.native("Swiper", listOf(pager.controller), call,
            listOf(EtsUiForEach(indexItems(pager.count, call), EtsParameter(binding(parameter).symbol), body(fn.body!!, child), source)))
            .copy(attributes = listOf(
                target.attribute("index", listOf(pager.current), call),
                target.attribute("loop", listOf(target.literal(false, call)), call),
                target.attribute("indicator", listOf(target.literal(false, call)), call),
                target.attribute("disableSwipe", listOf(EtsUnary("!", enabled, EtsTypes.BOOLEAN,
                    language.source(call))), call),
                target.attribute("onChange", listOf(onChange), call))), setOf("padding", "onClick"))
    }
}
