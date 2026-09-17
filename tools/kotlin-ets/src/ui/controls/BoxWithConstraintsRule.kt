@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.expressions.*

internal class ComposeBoxWithConstraintsRule(
    private val target: ArkUiCalls,
    private val content: (IrExpression, Scope) -> ConstraintContent,
    private val decorate: (IrExpression?, Scope, ComposeElement) -> List<EtsStatement>,
) : CallRule {
    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? = null

    override fun lowerUi(call: IrCall, language: Language, scope: Scope): List<EtsStatement>? {
        if (symbolName(call.symbol.owner) != "androidx.compose.foundation.layout.BoxWithConstraints") return null
        target.checkArguments(call, setOf("modifier", "contentAlignment", "propagateMinConstraints", "content"))
        argument(call, "propagateMinConstraints")?.let {
            if ((language.expression(it, scope) as? EtsLiteral)?.value != false)
                target.diagnostics.unsupported(it, "BoxWithConstraints propagateMinConstraints=true requires explicit child constraint propagation")
        }
        val body = argument(call, "content") ?: target.diagnostics.unsupported(call, "BoxWithConstraints requires content")
        val slot = content(body, scope)
        val alignment = argument(call, "contentAlignment")?.let { language.expression(it, scope) }
            ?: target.enumValue("Alignment", "TopStart", call)
        fun invoke(width: Boolean, height: Boolean) = target.call("EtsComposeBoxWithConstraints", listOf(target.record("BoxConstraintsOptions", linkedMapOf(
            "content" to slot.builder, "data" to slot.data, "alignment" to alignment, "fixedWidth" to target.literal(width, call),
            "fixedHeight" to target.literal(height, call)), call)), call, identity = "compose:boxConstraints")
        val element = ComposeElement(EtsUiElement(invoke(false, false)), setOf("padding", "backgroundColor"),
            orderedArguments = listOf(alignment))
        fun constrain(statement: EtsStatement): EtsStatement = when (statement) {
            is EtsIf -> statement.copy(branches = statement.branches.map { it.copy(body = it.body.map(::constrain)) })
            is EtsUiElement -> {
                val nested = statement.copy(children = statement.children?.map(::constrain))
                if ((nested.call.callee as? EtsReference)?.symbol?.id == "compose:boxConstraints") {
                    val names = nested.attributes.map { (it.callee as? EtsReference)?.symbol?.name }
                    nested.copy(call = invoke("width" in names, "height" in names))
                } else nested
            }
            else -> statement
        }
        return decorate(argument(call, "modifier"), scope, element).map(::constrain)
    }
}
