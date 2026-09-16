@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.declarations.IrValueParameter
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.classOrNull

/** A supported List UI loop must retain its children even when effects inside are omitted. */
internal class ComposeForEachRule(private val target: ArkUiCalls,
    private val bind: (IrValueParameter) -> EtsReference,
    private val body: (IrBody, Scope) -> List<EtsStatement>) : CallRule {
    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? = null
    override fun lowerUi(call: IrCall, language: Language, scope: Scope): List<EtsStatement>? {
        if (sourceFile(call.symbol.owner) != null || symbolName(call.symbol.owner) != "kotlin.collections.forEach") return null
        val receiver = call.extensionReceiver ?: return null
        if (receiver.type.classOrNull?.owner?.let(::symbolName) !in setOf("kotlin.collections.List", "kotlin.collections.MutableList"))
            target.diagnostics.unsupported(call, "UI forEach requires a List receiver")
        target.checkArguments(call, setOf("action"))
        val action = lambda(argument(call, "action"), scope) ?: target.diagnostics.unsupported(call, "UI forEach requires a source lambda")
        val parameter = action.valueParameters.singleOrNull() ?: target.diagnostics.unsupported(call, "UI forEach requires one item parameter")
        val child = scope.fork()
        val value = bind(parameter)
        child.bindings[parameter.symbol] = value
        return listOf(EtsUiForEach(language.expression(receiver, scope), EtsParameter(value.symbol),
            body(action.body ?: target.diagnostics.unsupported(call, "UI forEach requires a body"), child), language.source(call)))
    }
}
