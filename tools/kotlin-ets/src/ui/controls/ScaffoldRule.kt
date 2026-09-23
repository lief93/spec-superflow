@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.expressions.IrExpression

internal class ComposeScaffoldRule(
    private val target: ArkUiCalls,
    private val content: (IrExpression, Scope) -> List<EtsStatement>,
    private val body: (IrExpression, Scope, EtsExpression) -> List<EtsStatement>,
    decorate: (IrExpression?, Scope, ComposeElement) -> List<EtsStatement>,
) : ComposeControlRule(decorate) {
    override fun control(call: IrCall, language: Language, scope: Scope): ComposeElement? {
        if (symbolName(call.symbol.owner) != "androidx.compose.material3.Scaffold") return null
        target.checkArguments(call, setOf("modifier", "topBar", "snackbarHost", "content"))
        val contentSource = argument(call, "content")
            ?: target.diagnostics.unsupported(call, "Scaffold requires content")
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

        val topBar = argument(call, "topBar")
        val topInset = if (topBar == null) target.literal(0, call) else target.literal(64, call)
        val contentPadding = edgePadding(listOf(target.literal(0, call), topInset,
            target.literal(0, call), target.literal(0, call)), at)
        val page = target.native("Stack", listOf(target.stackOptions(call)), call,
            body(contentSource, child, contentPadding)).copy(attributes = listOf(
            target.attribute("width", listOf(target.literal("100%", call)), call),
            target.attribute("height", listOf(target.literal("100%", call)), call)))
        val layers = mutableListOf<EtsStatement>(page)
        topBar?.let { layers += content(it, child) }
        argument(call, "snackbarHost")?.let { layers += content(it, child) }
        val scaffold = target.native("Stack", listOf(target.stackOptions(call)), call, layers).copy(attributes = listOf(
            target.attribute("backgroundColor", listOf(EtsMember(scheme, "background", EtsTypes.NUMBER, at)), call)))
        return ComposeElement(scaffold, modifierBoundaries = setOf("backgroundColor"))
    }
}
