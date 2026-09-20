@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.classOrNull

internal class ComposeClickableTextRule(
    private val target: ArkUiCalls,
    decorate: (IrExpression?, Scope, ComposeElement) -> List<EtsStatement>,
) : ComposeControlRule(decorate) {
    override fun control(call: IrCall, language: Language, scope: Scope): ComposeElement? {
        if (symbolName(call.symbol.owner) != "androidx.compose.foundation.text.ClickableText") return null
        target.checkArguments(call, setOf("text", "modifier", "style", "onClick"), setOf("softWrap", "overflow", "maxLines"))
        val text = argument(call, "text") ?: target.diagnostics.unsupported(call, "ClickableText requires text")
        if (text.type.classOrNull?.owner?.let(::symbolName) != "androidx.compose.ui.text.AnnotatedString")
            target.diagnostics.unsupported(text, "ClickableText requires AnnotatedString")
        val click = argument(call, "onClick") ?: target.diagnostics.unsupported(call, "ClickableText requires onClick")
        val at = language.source(call)
        val annotated = language.expression(text, scope)
        val fallback = argument(call, "style")?.let { language.expression(it, scope) }
        val color = fallback?.let { EtsBinary("??", EtsMember(it, "color", EtsNullableType(EtsTypes.NUMBER), at),
            target.literal(0xFF000000L, call), EtsTypes.NUMBER, at) } ?: target.literal(0xFF000000L, call)
        val weight = fallback?.let { EtsBinary("??", EtsMember(it, "fontWeight", EtsNullableType(EtsTypes.NUMBER), at),
            target.literal(400, call), EtsTypes.NUMBER, at) } ?: target.literal(400, call)
        val spans = EtsMember(annotated, "spans", annotatedSpansType, at)
        val item = EtsSymbol("ui:annotated-span:${at.start}", "span", annotatedSpanType, at)
        val itemRef = EtsReference(item)
        val fn = lambda(click, scope) ?: target.diagnostics.unsupported(click, "ClickableText requires a source onClick lambda")
        val offset = fn.valueParameters.singleOrNull()
            ?: target.diagnostics.unsupported(fn, "ClickableText onClick requires an Int offset")
        val child = scope.fork()
        val offsetSymbol = EtsSymbol("ui:click-offset:${at.start}", offset.name.asString(), EtsTypes.NUMBER, at)
        child.bindings[offset.symbol] = EtsReference(offsetSymbol)
        val handler = language.statements(fn.body ?: target.diagnostics.unsupported(fn, "ClickableText requires an onClick body"), child)
        val start = EtsMember(itemRef, "start", EtsTypes.NUMBER, at)
        val end = EtsMember(itemRef, "end", EtsTypes.NUMBER, at)
        val offsetInSpan = EtsConditional(EtsBinary(">", end, start, EtsTypes.BOOLEAN, at),
            EtsBinary("-", end, target.literal(1, call), EtsTypes.NUMBER, at), start, EtsTypes.NUMBER, at)
        val invoke = EtsCall(EtsLambda(listOf(EtsParameter(offsetSymbol)), handler, EtsTypes.VOID, at),
            listOf(offsetInSpan), EtsTypes.VOID, at)
        val spanColor = EtsBinary("??", EtsMember(itemRef, "color", EtsNullableType(EtsTypes.NUMBER), at), color, EtsTypes.NUMBER, at)
        val spanWeight = EtsBinary("??", EtsMember(itemRef, "fontWeight", EtsNullableType(EtsTypes.NUMBER), at), weight, EtsTypes.NUMBER, at)
        val span = target.native("Span", listOf(EtsMember(itemRef, "text", EtsTypes.STRING, at)), call).copy(attributes = listOf(
            target.attribute("fontColor", listOf(spanColor), call),
            target.attribute("fontWeight", listOf(spanWeight), call),
            target.attribute("onClick", listOf(EtsLambda(emptyList(), listOf(EtsExpressionStatement(invoke)), EtsTypes.VOID, at)), call),
        ))
        val visible = EtsIf(listOf(EtsBranch(EtsMember(itemRef, "display", EtsTypes.BOOLEAN, at), listOf(span))), at)
        val attrs = listOf(target.attribute("align", listOf(target.enumValue("Alignment", "TopStart", call)), call)) +
            listOfNotNull(fallback?.let { target.attribute("attributeModifier", listOf(textStyleModifier(
                textStyleArgumentOrder.map { name ->
                    when (name) {
                        "style" -> it
                        "overflow" -> target.enumValue("TextOverflow", "Clip", call)
                        "maxLines" -> target.literal(Int.MAX_VALUE, call)
                        else -> EtsLiteral(null, EtsTypes.NULL, at)
                    }
                } + color, at)), call) })
        return ComposeElement(target.native("Text", listOf(target.literal("", call)), call,
            listOf(EtsUiForEach(spans, EtsParameter(item), listOf(visible), at))).copy(attributes = attrs),
            orderedArguments = listOfNotNull(fallback))
    }
}
