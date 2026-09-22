@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.compose

import dev.ets.*
import dev.ets.widgets.Children
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.IrStatement
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.symbols.IrValueSymbol
import org.jetbrains.kotlin.ir.types.*
import org.jetbrains.kotlin.ir.util.fqNameWhenAvailable
import org.jetbrains.kotlin.ir.util.hasAnnotation
import org.jetbrains.kotlin.ir.visitors.IrElementVisitorVoid
import org.jetbrains.kotlin.ir.visitors.acceptChildrenVoid
import org.jetbrains.kotlin.ir.visitors.acceptVoid
import org.jetbrains.kotlin.name.FqName

/** Resolved source composables become named builders; composable lambdas remain structured slots. */
class ComposeHelperLowering(private val backend: EtsBackend, private val diagnostics: DiagnosticSink,
    pagers: Map<IrValueSymbol, ComposeStateLowering.PagerStateBinding> = emptyMap()) {
    data class Plan(
        val signature: EtsFunction,
        val model: Children<EtsExpression, SourceSpan>,
        val sourcePath: String,
    )

    private val composable = FqName("androidx.compose.runtime.Composable")
    private val wrappedBuilder = EtsNamedType("WrappedBuilder", listOf(EtsTupleType(emptyList())), external = true)
    private val helpers = linkedMapOf<IrSimpleFunction, Plan>()
    private val helperNames = linkedMapOf<String, IrSimpleFunction>()
    private val slotPlans = linkedMapOf<String, Plan>()
    private val active = linkedSetOf<IrSimpleFunction>()
    private val owners = mutableListOf<IrFunction>()
    private val slotSymbols = linkedSetOf<IrValueSymbol>()
    private val adapter = ComposeWidgetAdapter(backend.language, diagnostics, ::sourceCall, pagers)

    fun lowerEntry(function: IrSimpleFunction, scope: Scope,
        handledStatements: Set<IrStatement>): Children<EtsExpression, SourceSpan> = withOwner(function) {
        adapter.lower(function, scope, handledStatements)
    }

    fun plans(): List<Plan> = helpers.values.toList() + slotPlans.values

    private fun sourceCall(call: IrCall, scope: Scope): EtsExpression? {
        slot(call, scope)?.let { return it }
        val function = call.symbol.owner
        if (!function.hasAnnotation(composable) || !function.returnType.isUnit() || sourceFile(function) == null || function.isExternal)
            return null
        if (function.typeParameters.isNotEmpty())
            diagnostics.unsupported(call, "Generic source composables are outside the widget helper profile")
        if (function.extensionReceiverParameter != null || function.dispatchReceiverParameter != null)
            diagnostics.unsupported(call, "Source composable helpers must be top-level functions without receivers")
        if (function in active)
            diagnostics.unsupported(call, "Recursive source composable calls are outside the widget helper profile")
        val plan = helpers[function] ?: build(function)
        val arguments = function.valueParameters.mapIndexed { index, parameter ->
            val value = call.getValueArgument(index)
            if (slotParameter(parameter)) {
                if (value == null) diagnostics.unsupported(call,
                    "Composable content parameter ${parameter.name} requires an explicit structured slot")
                slotArgument(value, parameter, scope)
            } else value?.let { backend.language.expression(it, scope) }
                ?: if (parameter.defaultValue != null) EtsUndefined(backend.language.source(call))
                else diagnostics.unsupported(call, "Missing source composable argument: ${parameter.name}")
        }
        return EtsCall(EtsReference(plan.signature.symbol, backend.language.source(call)), arguments,
            EtsTypes.VOID, backend.language.source(call))
    }

    private fun build(function: IrSimpleFunction): Plan {
        helperNames[function.name.asString()]?.takeIf { it !== function }?.let {
            diagnostics.unsupported(function, "Overloaded source composables cannot preserve one target method name")
        }
        helperNames[function.name.asString()] = function
        active += function
        try {
            function.valueParameters.filter(::slotParameter).forEach { parameter ->
                if (!contentSlotType(parameter.type))
                    diagnostics.unsupported(parameter, "Composable content slots currently require () -> Unit")
                if (parameter.defaultValue != null)
                    diagnostics.unsupported(parameter, "Composable content defaults cannot replace an explicit slot")
            }
            val scope = Scope()
            val ordinary = backend.parameters(function, scope)
            val parameters = function.valueParameters.mapIndexed { index, parameter ->
                if (!slotParameter(parameter)) ordinary[index] else {
                    slotSymbols += parameter.symbol
                    val source = backend.language.source(parameter)
                    val target = EtsParameter(EtsSymbol("compose-helper-slot:${source.file}:${source.start}:${parameter.name}",
                        parameter.name.asString(), wrappedBuilder, source))
                    scope.bindings[parameter.symbol] = EtsReference(target.symbol)
                    target
                }
            }
            val shell = EtsFunction(function.name.asString(), parameters, EtsTypes.VOID, emptyList(),
                backend.language.source(function), exported = true, builder = true)
            val model = withOwner(function) { adapter.lowerFunctionBody(function, scope) }
            val path = backend.language.source(function).file
                ?: diagnostics.unsupported(function, "Source composable helper requires a source file")
            return Plan(shell, model, path).also { helpers[function] = it }
        } finally {
            active -= function
        }
    }

    private fun slot(call: IrCall, scope: Scope): EtsExpression? {
        if (call.symbol.owner.name.asString() != "invoke") return null
        val receiver = (call.dispatchReceiver ?: call.extensionReceiver) as? IrGetValue ?: return null
        if (receiver.symbol !in slotSymbols) return null
        if (call.valueArgumentsCount != 0)
            diagnostics.unsupported(call, "Composable content slot invocation requires no arguments")
        val value = scope.bindings[receiver.symbol]
            ?: diagnostics.unsupported(receiver, "Unbound composable content slot: ${receiver.symbol.owner.name}")
        return EtsCall(EtsMember(value, "builder", EtsFunctionType(emptyList(), EtsTypes.VOID),
            backend.language.source(call)), emptyList(), EtsTypes.VOID, backend.language.source(call))
    }

    private fun slotArgument(expression: IrExpression, parameter: IrValueParameter, scope: Scope): EtsExpression {
        val existing = expression as? IrGetValue
        if (existing != null && existing.symbol in slotSymbols) return scope.bindings[existing.symbol]
            ?: diagnostics.unsupported(existing, "Unbound forwarded composable content slot")
        val function = lambda(expression, scope)
            ?: diagnostics.unsupported(expression, "Composable content requires a direct or forwarded lambda")
        if (function.valueParameters.isNotEmpty())
            diagnostics.unsupported(function, "Composable content slots currently require () -> Unit")
        val owner = owners.lastOrNull()
            ?: diagnostics.unsupported(expression, "Composable content requires an owning source function")
        val name = "${owner.name}_${parameter.name}"
        if (name in slotPlans)
            diagnostics.unsupported(expression, "Repeated composable slot name cannot be expanded into numbered methods: $name")
        val used = linkedSetOf<IrValueSymbol>()
        function.body?.acceptVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) = element.acceptChildrenVoid(this)
            override fun visitGetValue(expression: IrGetValue) {
                if (expression.symbol in scope.bindings) used += expression.symbol
                super.visitGetValue(expression)
            }
        })
        val captures = scope.bindings.filterKeys { it in used }
        val names = linkedSetOf<String>()
        val bridgeParameters = captures.map { (symbol, value) ->
            val source = backend.language.source(symbol.owner)
            val sourceName = symbol.owner.name.asString()
            if (!names.add(sourceName)) diagnostics.unsupported(function,
                "Composable slot captures cannot bind duplicate parameter name: $sourceName")
            EtsParameter(EtsSymbol("compose-slot:${source.file}:${function.startOffset}:$sourceName",
                sourceName, value.type, source))
        }
        val child = scope.fork()
        captures.keys.zip(bridgeParameters).forEach { (symbol, target) ->
            child.bindings[symbol] = EtsReference(target.symbol)
        }
        val model = withOwner(function) { adapter.lowerFunctionBody(function, child) }
        val source = backend.language.source(function)
        val shell = EtsFunction(name, bridgeParameters, EtsTypes.VOID, emptyList(), source,
            exported = false, builder = true)
        val path = source.file ?: diagnostics.unsupported(function, "Composable slot requires a source file")
        slotPlans[name] = Plan(shell, model, path)
        // WrappedBuilder owns the UI invocation boundary. Its callback calls the
        // declared builder by the same typed symbol without treating it as inline UI DSL.
        val call = EtsCall(EtsReference(shell.symbol.copy(external = true), source),
            captures.values.toList(), EtsTypes.VOID, source)
        val callback = EtsLambda(emptyList(), listOf(EtsExpressionStatement(call)), EtsTypes.VOID, source)
        return EtsNew(wrappedBuilder, listOf(callback), backend.language.source(expression))
    }

    private fun slotParameter(parameter: IrValueParameter): Boolean = parameter.type.hasAnnotation(composable)

    private fun contentSlotType(type: IrType): Boolean {
        val simple = type as? IrSimpleType ?: return false
        val owner = simple.classOrNull?.owner?.fqNameWhenAvailable?.asString()
        val result = (simple.arguments.singleOrNull() as? IrTypeProjection)?.type
        return owner == "kotlin.Function0" && result?.isUnit() == true
    }

    private inline fun <T> withOwner(owner: IrFunction, emit: () -> T): T {
        owners += owner
        return try { emit() } finally { owners.removeAt(owners.lastIndex) }
    }
}
