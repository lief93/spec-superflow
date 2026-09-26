@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.IrStatement
import org.jetbrains.kotlin.ir.expressions.*

/** Maps the common main-scope delay pattern to the target event-loop timer.
 * Coroutine values, jobs and arbitrary dispatchers remain outside this rule.
 */
internal class CoroutineTimerRule(private val diagnostics: DiagnosticSink) : CallRule {
    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? = null

    override fun lowerStatement(call: IrCall, language: Language, scope: Scope): List<EtsStatement>? {
        if (symbolName(call.symbol.owner) != "kotlinx.coroutines.launch") return null
        val receiver = resolveExpression(call.dispatchReceiver ?: call.extensionReceiver, scope) as? IrCall
            ?: return null
        if (symbolName(receiver.symbol.owner) != "kotlinx.coroutines.CoroutineScope") return null
        val context = argument(receiver, "context")?.let { resolveExpression(it, scope) } as? IrCall
            ?: diagnostics.unsupported(receiver, "CoroutineScope timer requires Dispatchers.Main")
        val contextName = context.symbol.owner.correspondingPropertySymbol?.owner?.let(::symbolName)
            ?: symbolName(context.symbol.owner)
        if (contextName !in setOf("kotlinx.coroutines.Dispatchers.Main",
                "kotlinx.coroutines.Dispatchers.<get-Main>"))
            diagnostics.unsupported(context, "CoroutineScope timer requires Dispatchers.Main")
        call.symbol.owner.valueParameters.forEachIndexed { index, parameter ->
            call.getValueArgument(index)?.takeIf { parameter.name.asString() != "block" }?.let {
                diagnostics.unsupported(it,
                    "Coroutine timer launch does not support explicit ${parameter.name} semantics")
            }
        }
        val blockExpression = argument(call, "block")
            ?: diagnostics.unsupported(call, "Coroutine timer launch requires a block")
        val block = lambda(blockExpression, scope)
            ?: diagnostics.unsupported(blockExpression, "Coroutine timer launch requires a direct source lambda")
        val statements = (block.body as? IrBlockBody)?.statements
            ?: diagnostics.unsupported(block, "Coroutine timer launch requires a block body")
        val delay = statements.firstOrNull()?.let(::statementExpression) as? IrCall ?: return null
        if (statements.size < 2 || symbolName(delay.symbol.owner) != "kotlinx.coroutines.delay") return null
        val duration = argument(delay, "timeMillis")
            ?: diagnostics.unsupported(delay, "delay requires timeMillis")
        val at = language.source(call)
        val callback = EtsLambda(emptyList(), language.statements(statements.drop(1), scope.fork()),
            EtsTypes.VOID, language.source(blockExpression))
        val sourceDuration = language.expression(duration, scope)
        val milliseconds = if (sourceDuration.type == EtsTypes.NUMBER) sourceDuration else
            EtsCall(EtsReference(EtsSymbol("target:Number", "Number",
                EtsFunctionType(listOf(sourceDuration.type), EtsTypes.NUMBER), at, external = true)),
                listOf(sourceDuration), EtsTypes.NUMBER, at)
        val timer = EtsReference(EtsSymbol("target:setTimeout", "setTimeout",
            EtsFunctionType(listOf(callback.type, EtsTypes.NUMBER), EtsTypes.NUMBER), at, external = true))
        return listOf(EtsExpressionStatement(EtsCall(timer, listOf(callback, milliseconds),
            EtsTypes.NUMBER, at)))
    }

    private fun statementExpression(statement: IrStatement): IrExpression? = when (statement) {
        is IrReturn -> statement.value
        is IrTypeOperatorCall -> if (statement.operator == IrTypeOperator.IMPLICIT_COERCION_TO_UNIT)
            statement.argument else statement
        is IrContainerExpression -> statement.statements.singleOrNull()?.let(::statementExpression)
        is IrExpression -> statement
        else -> null
    }
}
