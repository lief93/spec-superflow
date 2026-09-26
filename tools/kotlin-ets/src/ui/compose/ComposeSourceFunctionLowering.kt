@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.compose

import dev.ets.*
import dev.ets.widgets.*
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.IrStatement
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.symbols.IrValueSymbol
import org.jetbrains.kotlin.ir.types.*
import org.jetbrains.kotlin.ir.util.fqNameWhenAvailable
import org.jetbrains.kotlin.ir.util.hasAnnotation
import org.jetbrains.kotlin.ir.util.isNullable as isNullableType
import org.jetbrains.kotlin.ir.visitors.IrElementVisitorVoid
import org.jetbrains.kotlin.ir.visitors.acceptChildrenVoid
import org.jetbrains.kotlin.ir.visitors.acceptVoid
import org.jetbrains.kotlin.name.FqName

/**
 * Adds Compose function-body semantics to the shared language function lowering.
 * This pass never owns Kotlin function names, defaults, visibility or generics.
 */
class ComposeSourceFunctionLowering(private val backend: EtsBackend, private val diagnostics: DiagnosticSink,
    pagers: Map<IrValueSymbol, ComposeStateLowering.PagerStateBinding> = emptyMap(),
    scrolls: Map<IrValueSymbol, ComposeStateLowering.ScrollStateBinding> = emptyMap(),
    lazyLists: Map<IrValueSymbol, ComposeStateLowering.LazyListStateBinding> = emptyMap(),
    widgetRules: List<ComposeWidgetRule> = emptyList(),
    private val materialContextRequired: Boolean = false,
    private val componentType: EtsNamedType? = null) {
    data class Plan(
        val signature: EtsFunction,
        val model: Children<EtsExpression, SourceSpan>,
        val sourcePath: String,
        val componentMember: Boolean = false,
        val layoutScope: WidgetLayoutScope? = null,
    )

    private val composable = FqName("androidx.compose.runtime.Composable")
    private val helpers = linkedMapOf<IrSimpleFunction, Plan>()
    private val slotPlans = linkedMapOf<String, Plan>()
    private val activeSlotNames = linkedSetOf<String>()
    private val active = linkedSetOf<IrSimpleFunction>()
    private val owners = mutableListOf<IrFunction>()
    private val componentOwnership = mutableListOf<Boolean>()
    private data class SlotContract(val sourceParameters: List<EtsType>,
        val invocationParameters: List<EtsType>,
        val receiverScope: WidgetLayoutScope?)
    private val slotSymbols = linkedMapOf<IrValueSymbol, SlotContract>()
    private val adapter = ComposeWidgetAdapter(backend.language, diagnostics, ::sourceWidget,
        pagers, scrolls, lazyLists, widgetRules, ::sourceContent)

    fun lowerEntry(function: IrSimpleFunction, scope: Scope,
        handledStatements: Set<IrStatement>): Children<EtsExpression, SourceSpan> = withOwner(function) {
        adapter.lower(function, scope, handledStatements)
    }

    fun lowerEntryPlan(function: IrSimpleFunction, scope: Scope,
        handledStatements: Set<IrStatement>, semantics: FunctionTargetSemantics): Plan =
        plan(function, scope, includeFrameworkContext = false, semantics = semantics,
            componentMember = true) { nested ->
        adapter.lower(function, nested, handledStatements)
    }

    fun plans(): List<Plan> = helpers.values.toList() + slotPlans.values

    private fun sourceWidget(call: IrCall, scope: Scope,
        parent: WidgetLayoutScope?): Widget<EtsExpression, SourceSpan>? {
        slot(call, scope)?.let { return Widget.BuilderCall(it, backend.language.source(call)) }
        val function = call.symbol.owner
        if (!function.hasAnnotation(composable) || !function.returnType.isUnit() || sourceFile(function) == null || function.isExternal)
            return null
        if (function.extensionReceiverParameter != null || function.dispatchReceiverParameter != null)
            diagnostics.unsupported(call, "Source composable functions with receivers are not yet supported")
        if (function in active)
            diagnostics.unsupported(call, "Recursive source composable calls are outside the widget helper profile")
        if (function.valueParameters.any { parameter ->
                modifierParameter(parameter) && call.getValueArgument(parameter.index) != null
            }) return inlineSourceWidget(call, function, scope, parent)
        val plan = helpers[function] ?: build(function)
        val arguments = implicitContextArguments(scope, call) + function.valueParameters.mapIndexed { index, parameter ->
            val value = call.getValueArgument(index)
            if (slotParameter(parameter)) {
                if (value == null) diagnostics.unsupported(call,
                    "Composable content parameter ${parameter.name} requires an explicit structured slot")
                slotArgument(value, parameter, scope, function)
            } else value?.let { backend.language.expression(it, scope) }
                ?: if (parameter.defaultValue != null) EtsUndefined(backend.language.source(call))
                else diagnostics.unsupported(call, "Missing source composable argument: ${parameter.name}")
        }
        val typeArguments = function.typeParameters.indices.map { index ->
            backend.language.type(call.getTypeArgument(index)
                ?: diagnostics.unsupported(call, "Missing source composable type argument"))
        }
        return Widget.BuilderCall(EtsCall(EtsReference(plan.signature.symbol, backend.language.source(call)), arguments,
            EtsTypes.VOID, backend.language.source(call), typeArguments), backend.language.source(call))
    }

    private fun inlineSourceWidget(call: IrCall, function: IrSimpleFunction, scope: Scope,
        parent: WidgetLayoutScope?): Widget<EtsExpression, SourceSpan> {
        if (function.valueParameters.any(::slotParameter)) diagnostics.unsupported(call,
            "A source composable with explicit Modifier arguments and content slots requires a target component adapter")
        val nested = scope.fork()
        function.valueParameters.forEach { parameter ->
            val explicit = call.getValueArgument(parameter.index)
            val value = explicit ?: parameter.defaultValue?.expression
                ?: diagnostics.unsupported(call, "Missing source composable argument: ${parameter.name}")
            if (modifierParameter(parameter)) nested.aliases[parameter.symbol] = value
            else nested.bindings[parameter.symbol] = backend.language.expression(value,
                if (explicit == null) nested else scope)
        }
        active += function
        return try {
            val children = withOwner(function) { adapter.lowerFunctionBody(function, nested, parent) }
            Widget.Group(children, backend.language.source(call))
        } finally {
            active -= function
        }
    }

    private fun modifierParameter(parameter: IrValueParameter): Boolean =
        parameter.type.classFqName?.asString() in setOf(
            "androidx.compose.ui.Modifier", "androidx.compose.ui.Modifier.Companion")

    private fun build(function: IrSimpleFunction): Plan {
        val result = plan(function, Scope(), includeFrameworkContext = true) {
            scope -> adapter.lowerFunctionBody(function, scope)
        }
        helpers[function] = result
        return result
    }

    private fun plan(function: IrSimpleFunction, initialScope: Scope,
        includeFrameworkContext: Boolean = true,
        semantics: FunctionTargetSemantics = FunctionTargetSemantics(),
        componentMember: Boolean = false,
        lowerBody: (Scope) -> Children<EtsExpression, SourceSpan>): Plan {
        active += function
        componentOwnership += componentMember
        try {
            function.valueParameters.filter(::slotParameter).forEach { parameter ->
                slotParameterTypes(parameter)
                if (parameter.defaultValue != null)
                    diagnostics.unsupported(parameter, "Composable content defaults cannot replace an explicit slot")
            }
            function.valueParameters.filter(::slotParameter).forEach {
                slotSymbols[it.symbol] = slotContract(it)
            }
            lateinit var model: Children<EtsExpression, SourceSpan>
            val shell = IrFunctionToEts.lower(function, backend.language, initialScope, FunctionTargetSemantics(
                builder = true,
                frameworkParameters = { scope ->
                    semantics.frameworkParameters(scope) +
                        if (includeFrameworkContext) bindImplicitContextParameters(function, scope) else emptyList()
                },
                parameterType = { parameter, defaultType ->
                    if (!slotParameter(parameter)) semantics.parameterType(parameter, defaultType) else {
                        val slotType = wrappedBuilderType(slotContract(parameter).invocationParameters)
                        if (parameter.type.isNullableType()) EtsNullableType(slotType) else slotType
                    }
                },
                parameterBinding = semantics.parameterBinding,
                retainSourceDefault = semantics.retainSourceDefault,
                body = { _, scope ->
                    model = withOwner(function) { lowerBody(scope) }
                    emptyList()
                },
            ))
            val path = backend.language.source(function).file
                ?: diagnostics.unsupported(function, "Source composable function requires a source file")
            return Plan(shell.copy(kind = if (componentMember) EtsFunctionKind.METHOD else shell.kind,
                exported = if (componentMember) false else shell.exported,
                visibility = if (componentMember) EtsVisibility.PRIVATE else shell.visibility),
                model, path, componentMember)
        } finally {
            componentOwnership.removeAt(componentOwnership.lastIndex)
            active -= function
        }
    }

    private fun slot(call: IrCall, scope: Scope): EtsExpression? {
        if (call.symbol.owner.name.asString() != "invoke") return null
        val receiver = slotReceiver(invocationReceiver(call), scope) ?: return null
        val contract = slotSymbols[receiver.symbol] ?: return null
        val arguments = (0 until call.valueArgumentsCount).mapNotNull(call::getValueArgument)
        if (arguments.size != contract.sourceParameters.size)
            diagnostics.unsupported(call,
                "Composable content slot invocation requires ${contract.sourceParameters.size} arguments")
        val loweredArguments = arguments.zip(contract.sourceParameters).map { (argument, expected) ->
            val lowered = backend.language.expression(argument, scope)
            if (lowered.type != expected) diagnostics.unsupported(argument,
                "Composable content slot argument requires $expected, got ${lowered.type}")
            lowered
        }
        val binding = scope.bindings[receiver.symbol]
            ?: diagnostics.unsupported(receiver, "Unbound composable content slot: ${receiver.symbol.owner.name}")
        val wrappedType = wrappedBuilderType(contract.invocationParameters)
        val value = if (binding.type is EtsNullableType) EtsCast(binding, wrappedType,
            backend.language.source(call)) else binding
        val invocationArguments = implicitContextArguments(scope, call) + loweredArguments
        return EtsCall(EtsMember(value, "builder",
            EtsFunctionType(contract.invocationParameters, EtsTypes.VOID),
            backend.language.source(call)), invocationArguments, EtsTypes.VOID, backend.language.source(call))
    }

    private fun sourceContent(expression: IrExpression, scope: Scope,
        parent: WidgetLayoutScope?): Children<EtsExpression, SourceSpan>? {
        val receiver = slotReceiver(expression, scope) ?: return null
        val contract = slotSymbols[receiver.symbol] ?: return null
        if (contract.receiverScope != null && parent != contract.receiverScope)
            diagnostics.unsupported(expression,
                "Composable receiver slot requires ${contract.receiverScope} content scope, got $parent")
        if (contract.sourceParameters.isNotEmpty()) diagnostics.unsupported(expression,
            "A parameterized composable slot must be invoked with explicit arguments")
        val binding = scope.bindings[receiver.symbol]
            ?: diagnostics.unsupported(receiver, "Unbound forwarded composable content slot")
        val wrappedType = wrappedBuilderType(contract.invocationParameters)
        val value = if (binding.type is EtsNullableType)
            EtsCast(binding, wrappedType, backend.language.source(expression)) else binding
        val call = EtsCall(EtsMember(value, "builder",
            EtsFunctionType(contract.invocationParameters, EtsTypes.VOID),
            backend.language.source(expression)), implicitContextArguments(scope, expression),
            EtsTypes.VOID, backend.language.source(expression))
        return Children(listOf(Widget.BuilderCall(call, backend.language.source(expression))))
    }

    private fun slotArgument(expression: IrExpression, parameter: IrValueParameter, scope: Scope,
        callee: IrSimpleFunction): EtsExpression {
        val existing = expression as? IrGetValue
        if (existing != null && existing.symbol in slotSymbols) return scope.bindings[existing.symbol]
            ?: diagnostics.unsupported(existing, "Unbound forwarded composable content slot")
        val function = lambda(expression, scope)
            ?: diagnostics.unsupported(expression, "Composable content requires a direct or forwarded lambda")
        val contract = slotContract(parameter)
        if (function.valueParameters.size != contract.sourceParameters.size)
            diagnostics.unsupported(function,
                "Composable content slot requires ${contract.sourceParameters.size} parameters, got ${function.valueParameters.size}")
        val owner = owners.asReversed().firstOrNull { !it.name.isSpecial }
            ?: diagnostics.unsupported(expression, "Composable content requires an owning source function")
        val baseName = "${owner.name}_${parameter.name}"
        val occupiedNames = slotPlans.keys + activeSlotNames
        val name = if (baseName !in occupiedNames) baseName
            else "${owner.name}_${callee.name}_${parameter.name}"
        if (name in occupiedNames)
            diagnostics.unsupported(expression,
                "Repeated composable slot requires a distinct source helper or named component: $name")
        val used = linkedSetOf<IrValueSymbol>()
        val visitedAliases = linkedSetOf<IrValueSymbol>()
        val captureVisitor = object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) = element.acceptChildrenVoid(this)
            override fun visitGetValue(expression: IrGetValue) {
                when {
                    expression.symbol in scope.bindings -> used += expression.symbol
                    visitedAliases.add(expression.symbol) -> scope.aliases[expression.symbol]?.acceptVoid(this)
                }
                super.visitGetValue(expression)
            }
        }
        function.body?.acceptVoid(captureVisitor)
        val captures = scope.bindings.filterKeys { it in used }
        val names = linkedSetOf<String>()
        val contextParameters = implicitContextParameters(function)
        val slotParameters = function.valueParameters.zip(contract.sourceParameters).map { (sourceParameter, targetType) ->
            val source = backend.language.source(sourceParameter)
            EtsParameter(EtsSymbol("compose-slot:${source.file}:${function.startOffset}:argument:${sourceParameter.index}",
                sourceParameter.name.asString(), targetType, source))
        }
        val bridgeParameters = captures.map { (symbol, value) ->
            val source = backend.language.source(symbol.owner)
            val sourceName = symbol.owner.name.asString()
            if (!names.add(sourceName)) diagnostics.unsupported(function,
                "Composable slot captures cannot bind duplicate parameter name: $sourceName")
            EtsParameter(EtsSymbol("compose-slot:${source.file}:${function.startOffset}:$sourceName",
                sourceName, value.type, source))
        }
        val child = scope.fork()
        bindImplicitContextValues(child, contextParameters)
        function.valueParameters.zip(slotParameters).forEach { (source, target) ->
            child.bindings[source.symbol] = EtsReference(target.symbol)
        }
        captures.keys.zip(bridgeParameters).forEach { (symbol, target) ->
            child.bindings[symbol] = EtsReference(target.symbol)
        }
        activeSlotNames += name
        val model = try {
            withOwner(function) { adapter.lowerFunctionBody(function, child, parent = contract.receiverScope) }
        } finally {
            activeSlotNames -= name
        }
        val source = backend.language.source(function)
        val componentMember = componentOwnership.lastOrNull() == true && componentType != null
        val shell = EtsFunction(name, contextParameters + slotParameters + bridgeParameters,
            EtsTypes.VOID, emptyList(), source,
            kind = if (componentMember) EtsFunctionKind.METHOD else EtsFunctionKind.FUNCTION,
            exported = false, visibility = if (componentMember) EtsVisibility.PRIVATE else EtsVisibility.PUBLIC,
            builder = true)
        val path = source.file ?: diagnostics.unsupported(function, "Composable slot requires a source file")
        slotPlans[name] = Plan(shell, model, path, componentMember, contract.receiverScope)
        // WrappedBuilder owns the UI invocation boundary. Its callback calls the
        // declared builder by the same typed symbol without treating it as inline UI DSL.
        val callbackParameters = (contextParameters + slotParameters).mapIndexed { index, parameter ->
            EtsParameter(parameter.symbol.copy(id = "${parameter.symbol.id}:callback:$index"))
        }
        val target = if (componentMember) EtsMember(componentSelf(source), shell.name,
            shell.symbol.type, source, shell.symbol.id)
        else EtsReference(shell.symbol.copy(external = true), source)
        val call = EtsCall(target,
            callbackParameters.map { EtsReference(it.symbol) } + captures.values, EtsTypes.VOID, source)
        val callback = EtsLambda(callbackParameters, listOf(EtsExpressionStatement(call)), EtsTypes.VOID, source)
        return wrappedBuilder(contract.invocationParameters, callback, backend.language.source(expression))
    }

    private fun componentSelf(source: SourceSpan): EtsReference {
        val type = componentType ?: error("Component-owned slot requires a component type")
        return EtsReference(EtsSymbol("compose-slot:${source.file}:${source.start}:this",
            "this", type, source, external = true))
    }

    private fun implicitContextParameters(owner: IrFunction): List<EtsParameter> {
        if (!materialContextRequired) return emptyList()
        val source = backend.language.source(owner)
        return listOf(EtsParameter(EtsSymbol(
            "compose-context:${source.file}:${owner.startOffset}:material",
            "__etsMaterialContext", materialContextType, source)))
    }

    private fun bindImplicitContextValues(scope: Scope, parameters: List<EtsParameter>) {
        if (!materialContextRequired) return
        val parameter = parameters.singleOrNull()
            ?: error("Material invocation context requires one target parameter")
        scope.ambientValues[MATERIAL_CONTEXT] = EtsReference(parameter.symbol)
    }

    private fun bindImplicitContextParameters(owner: IrFunction, scope: Scope): List<EtsParameter> =
        implicitContextParameters(owner).also { bindImplicitContextValues(scope, it) }

    private fun implicitContextArguments(scope: Scope, owner: IrElement): List<EtsExpression> =
        if (materialContextRequired) listOf(materialContext(scope, backend.language.source(owner))) else emptyList()

    private fun slotContract(parameter: IrValueParameter): SlotContract {
        val source = slotParameterTypes(parameter)
        return SlotContract(source,
            (if (materialContextRequired) listOf(materialContextType) else emptyList()) + source,
            slotReceiverScope(parameter))
    }

    private fun slotParameter(parameter: IrValueParameter): Boolean = parameter.type.hasAnnotation(composable)

    private fun invocationReceiver(call: IrCall): IrExpression? {
        call.dispatchReceiver?.let { return it }
        call.extensionReceiver?.let { return it }
        call.arguments.firstOrNull { it != null }?.let { return it }
        var value: IrGetValue? = null
        call.acceptVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) {
                if (value == null) element.acceptChildrenVoid(this)
            }
            override fun visitGetValue(expression: IrGetValue) {
                if (value == null) value = expression
            }
        })
        return value
    }

    private fun slotReceiver(expression: IrExpression?, scope: Scope,
        visited: Set<IrValueSymbol> = emptySet()): IrGetValue? = when (expression) {
        is IrGetValue -> when {
            expression.symbol in slotSymbols -> expression
            expression.symbol in visited -> null
            else -> scope.aliases[expression.symbol]?.let { slotReceiver(it, scope, visited + expression.symbol) }
        }
        is IrTypeOperatorCall -> when (expression.operator) {
            IrTypeOperator.IMPLICIT_CAST, IrTypeOperator.IMPLICIT_COERCION_TO_UNIT,
            IrTypeOperator.IMPLICIT_NOTNULL -> slotReceiver(expression.argument, scope, visited)
            else -> null
        }
        else -> null
    }

    private fun slotParameterTypes(parameter: IrValueParameter): List<EtsType> {
        val type = parameter.type
        val simple = type as? IrSimpleType
            ?: diagnostics.unsupported(parameter, "Composable content slot requires a Kotlin function type")
        val owner = simple.classOrNull?.owner?.fqNameWhenAvailable?.asString()
        val arity = owner?.removePrefix("kotlin.Function")?.toIntOrNull()
            ?: diagnostics.unsupported(parameter, "Composable content slot requires a Kotlin function type")
        val arguments = simple.arguments.mapNotNull { (it as? IrTypeProjection)?.type }
        if (arguments.size != arity + 1 || arguments.lastOrNull()?.isUnit() != true)
            diagnostics.unsupported(parameter, "Composable content slot requires (...)->Unit")
        val parameters = arguments.dropLast(1)
        return (if (type.hasAnnotation(FqName("kotlin.ExtensionFunctionType"))) parameters.drop(1)
            else parameters).map(backend.language::type)
    }

    private fun slotReceiverScope(parameter: IrValueParameter): WidgetLayoutScope? {
        val type = parameter.type
        if (!type.hasAnnotation(FqName("kotlin.ExtensionFunctionType"))) return null
        val receiver = (type as? IrSimpleType)?.arguments?.firstOrNull()
            ?.let { it as? IrTypeProjection }?.type?.classFqName?.asString()
            ?: diagnostics.unsupported(parameter,
                "Composable receiver slot requires a resolved receiver type")
        return when (receiver) {
            "androidx.compose.foundation.layout.RowScope" -> WidgetLayoutScope.ROW
            "androidx.compose.foundation.layout.ColumnScope" -> WidgetLayoutScope.COLUMN
            "androidx.compose.foundation.layout.BoxScope" -> WidgetLayoutScope.BOX
            else -> null
        }
    }

    private inline fun <T> withOwner(owner: IrFunction, emit: () -> T): T {
        owners += owner
        return try { emit() } finally { owners.removeAt(owners.lastIndex) }
    }
}
