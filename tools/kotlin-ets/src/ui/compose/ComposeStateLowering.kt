@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.compose

import dev.ets.*
import java.util.Collections
import java.util.IdentityHashMap
import org.jetbrains.kotlin.ir.IrStatement
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.symbols.IrSimpleFunctionSymbol
import org.jetbrains.kotlin.ir.symbols.IrValueSymbol
import org.jetbrains.kotlin.ir.types.isBoolean
import org.jetbrains.kotlin.ir.types.isInt
import org.jetbrains.kotlin.ir.types.isString

/** Extracts the small Compose state profile before neutral widget adaptation. */
class ComposeStateLowering(private val language: Language, private val diagnostics: DiagnosticSink) {
    data class Plan(
        val fields: List<EtsField>,
        val scope: Scope,
        val handledStatements: Set<IrStatement>,
    )

    private data class State(
        val field: EtsField,
        val holder: IrValueSymbol,
        val getter: IrSimpleFunctionSymbol? = null,
        val setter: IrSimpleFunctionSymbol? = null,
    )

    fun lower(function: IrSimpleFunction, scope: Scope, componentName: String): Plan {
        diagnostics.currentFile = sourceFile(function)?.fileEntry?.name
        val statements = when (val body = function.body) {
            is IrBlockBody -> body.statements
            is IrExpressionBody -> listOf(body.expression)
            null -> diagnostics.unsupported(function, "Widget entry has no body")
            else -> diagnostics.unsupported(body, "Unsupported widget body")
        }
        val componentType = etsClassSymbol(componentName, language.source(function)).type
        val self = EtsReference(EtsSymbol("compose-state:${language.source(function).file}:${language.source(function).start}:this",
            "this", componentType, language.source(function), external = true))
        val handled = Collections.newSetFromMap(IdentityHashMap<IrStatement, Boolean>())
        val states = statements.mapNotNull { statement -> state(statement, scope, handled) }
        if (states.isEmpty()) return Plan(emptyList(), scope, handled)

        val holders = states.associateBy { it.holder }
        val getters = states.mapNotNull { state -> state.getter?.let { it to state } }.toMap()
        val setters = states.mapNotNull { state -> state.setter?.let { it to state } }.toMap()
        fun member(state: State, owner: IrExpression) = EtsMember(self, state.field.symbol.name,
            state.field.symbol.type, language.source(owner), state.field.symbol.id)
        fun assignment(call: IrCall, state: State, scope: Scope): EtsAssignment {
            val value = call.getValueArgument(0)
                ?: diagnostics.unsupported(call, "State update requires a value")
            return EtsAssignment(member(state, call), language.expression(value, scope), language.source(call))
        }
        val rule = object : CallRule {
            private fun direct(call: IrCall): State? {
                val property = call.symbol.owner.correspondingPropertySymbol?.owner?.let(::symbolName)
                if (property !in setOf("androidx.compose.runtime.State.value", "androidx.compose.runtime.MutableState.value")) return null
                return ((call.dispatchReceiver ?: call.extensionReceiver) as? IrGetValue)?.symbol?.let(holders::get)
            }

            override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
                getters[call.symbol]?.let { return member(it, call) }
                setters[call.symbol]?.let { return etsDiscard(assignment(call, it, scope), language.source(call)) }
                val state = direct(call) ?: return null
                return if (call.symbol.owner.valueParameters.isEmpty()) member(state, call)
                else etsDiscard(assignment(call, state, scope), language.source(call))
            }

            override fun lowerStatement(call: IrCall, language: Language, scope: Scope): List<EtsStatement>? {
                val state = setters[call.symbol] ?: direct(call)?.takeIf { call.symbol.owner.valueParameters.isNotEmpty() }
                    ?: return null
                return listOf(EtsExpressionStatement(assignment(call, state, scope)))
            }
        }
        val loweredScope = Scope(LinkedHashMap(scope.bindings), LinkedHashMap(scope.aliases), scope.callRule,
            listOf(rule) + scope.callRules, LinkedHashMap(scope.ambientValues))
        return Plan(states.map { it.field }, loweredScope, handled)
    }

    private fun state(statement: IrStatement, scope: Scope, handled: MutableSet<IrStatement>): State? {
        val declaration = when (statement) {
            is IrVariable -> StateDeclaration(statement.name.asString(), statement, statement.initializer,
                statement.symbol)
            is IrLocalDelegatedProperty -> StateDeclaration(statement.name.asString(), statement,
                statement.delegate.initializer, statement.delegate.symbol, statement.getter.symbol, statement.setter?.symbol)
            else -> return null
        }
        val initial = rememberedState(declaration.initializer ?: return null) ?: return null
        val targetType = when {
            initial.type.isBoolean() && initial is IrConst && initial.value is Boolean -> EtsTypes.BOOLEAN
            initial.type.isInt() && initial is IrConst && initial.value is Int -> EtsTypes.NUMBER
            initial.type.isString() && initial is IrConst && initial.value is String -> EtsTypes.STRING
            else -> diagnostics.unsupported(initial,
                "Compose state initially supports only direct Boolean, Int, and String initializers")
        }
        val at = language.source(declaration.owner)
        val targetName = "__etsState_${declaration.name}"
        val field = EtsField(EtsSymbol("compose-state:${at.file}:${at.start}:${declaration.name}",
            targetName, targetType, at), language.expression(initial, scope),
            visibility = EtsVisibility.PRIVATE, state = true)
        handled += statement
        return State(field, declaration.holder, declaration.getter, declaration.setter)
    }

    private data class StateDeclaration(
        val name: String,
        val owner: IrDeclaration,
        val initializer: IrExpression?,
        val holder: IrValueSymbol,
        val getter: IrSimpleFunctionSymbol? = null,
        val setter: IrSimpleFunctionSymbol? = null,
    )

    private fun rememberedState(expression: IrExpression): IrExpression? {
        val call = expression as? IrCall ?: return null
        val api = symbolName(call.symbol.owner)
        if (api == "androidx.compose.runtime.saveable.rememberSaveable")
            diagnostics.unsupported(call, "rememberSaveable is outside the Compose state Core Profile")
        if (api in setOf("androidx.compose.runtime.mutableStateOf", "androidx.compose.runtime.derivedStateOf"))
            diagnostics.unsupported(call, "Compose state declaration requires remember { mutableStateOf(initial) }")
        if (api != "androidx.compose.runtime.remember") return null
        call.symbol.owner.valueParameters.forEachIndexed { index, parameter ->
            if (call.getValueArgument(index) != null && parameter.name.asString() != "calculation")
                diagnostics.unsupported(call.getValueArgument(index)!!,
                    "Compose state remember does not support keys")
        }
        val calculation = argument(call, "calculation")
            ?: diagnostics.unsupported(call, "Compose state remember requires a calculation")
        val function = (calculation as? IrFunctionExpression)?.function
            ?: diagnostics.unsupported(calculation, "Compose state remember requires a direct lambda")
        val result = (function.body as? IrBlockBody)?.statements?.singleOrNull() as? IrReturn
            ?: diagnostics.unsupported(calculation, "Compose state remember requires one direct result")
        val factory = result.value as? IrCall
            ?: diagnostics.unsupported(result.value, "Compose state remember requires mutableStateOf")
        if (symbolName(factory.symbol.owner) != "androidx.compose.runtime.mutableStateOf")
            diagnostics.unsupported(factory, "Compose state remember supports only mutableStateOf")
        factory.symbol.owner.valueParameters.forEachIndexed { index, parameter ->
            if (factory.getValueArgument(index) != null && parameter.name.asString() != "value")
                diagnostics.unsupported(factory.getValueArgument(index)!!,
                    "Compose state mutableStateOf does not support a custom mutation policy")
        }
        return argument(factory, "value")
            ?: diagnostics.unsupported(factory, "Compose state mutableStateOf requires an initial value")
    }
}
