package dev.ets

/** ArkUI value parameters freeze outside an observed element. Use the SDK's
 * Binding contract for single-consumer state-dependent builder argument chains. */
fun bindReactiveBuilderArguments(program: EtsProgram): EtsProgram {
    val builders = linkedMapOf<String, EtsFunction>()
    val states = mutableSetOf<Pair<String?, String>>()
    program.files.forEach { file -> file.declarations.forEach { declaration ->
        walkEts(declaration) { if (it is EtsFunction && it.builder) builders[it.symbol.id] = it }
        if (declaration is EtsClass) declaration.members.filterIsInstance<EtsField>().filter { it.state }.forEach {
            states += declaration.symbol.id to it.symbol.name
        }
    } }
    fun id(call: EtsCall): String? = when (val target = call.callee) {
        is EtsReference -> target.symbol.id
        is EtsMember -> target.symbolId
        else -> null
    }
    val bound = linkedMapOf<String, EtsParameter>()
    val reactiveInputs = builders.values.flatMap { it.parameters }.filter { it.reactiveInput }.map { it.symbol.id }.toSet()
    val nativeBound = mutableSetOf<String>()
    fun nativeDependent(value: EtsExpression): Boolean {
        var result = false
        walkEts(value) { if (it is EtsReference && (it.symbol.id in reactiveInputs || it.symbol.id in nativeBound)) result = true }
        return result
    }
    fun dependent(value: EtsExpression): Boolean {
        var result = false
        walkEts(value) {
            if (it is EtsReference && (it.symbol.id in bound || it.symbol.id in reactiveInputs)) result = true
            if (it is EtsMember && (it.receiver.type as? EtsNamedType)?.symbolId to it.name in states) result = true
        }
        return result
    }
    do {
        val count = bound.size + nativeBound.size
        program.files.forEach { file -> file.declarations.forEach { declaration -> walkEts(declaration) { node ->
            if (node is EtsCall) builders[id(node)]?.parameters?.zip(node.arguments)?.forEach { (parameter, argument) ->
                if (parameter.symbol.type !is EtsFunctionType && dependent(argument)) bound[parameter.symbol.id] = parameter
                if (parameter.symbol.type !is EtsFunctionType && nativeDependent(argument)) nativeBound += parameter.symbol.id
            }
        } } }
    } while (count != bound.size + nativeBound.size)
    if (bound.isEmpty()) return program
    val parameters = mutableSetOf<String>()
    program.files.forEach { file -> file.declarations.forEach { declaration -> walkEts(declaration) { node ->
        when (node) {
            is EtsFunction -> parameters += node.parameters.map { it.symbol.id }
            is EtsLambda -> parameters += node.parameters.map { it.symbol.id }
            is EtsUiForEach -> parameters += node.item.symbol.id
            is EtsUiLazyForEach -> parameters += listOf(node.item.symbol.id, node.index.symbol.id)
            else -> Unit
        }
    } } }
    val fields = program.files.flatMap { it.declarations }.filterIsInstance<EtsClass>().flatMap { owner ->
        owner.members.filterIsInstance<EtsField>().map { (owner.symbol.id to it.symbol.name) to it }
    }.toMap()
    val snapshots = program.files.flatMap { it.declarations }.filterIsInstance<EtsClass>()
        .filter { it.valueSnapshot && snapshotConstructor(it) }.map { it.symbol.id }.toSet()
    fun initializationGuard(statement: EtsStatement): Boolean {
        val call = (statement as? EtsExpressionStatement)?.expression as? EtsCall ?: return false
        val callee = call.callee as? EtsReference ?: return false
        return call.arguments.isEmpty() && call.type == EtsTypes.VOID && callee.symbol.name.startsWith("__etsInitialize_")
    }
    fun returnedValue(function: EtsFunction): EtsExpression? = (function.body.lastOrNull() as? EtsReturn)?.value
    fun initializedTopLevelGetter(function: EtsFunction): Boolean {
        if (!function.symbol.name.startsWith("__etsGet_") || function.parameters.isNotEmpty() || function.body.size != 2 ||
            !initializationGuard(function.body.first())) return false
        fun storage(value: EtsExpression): EtsReference? = when (value) {
            is EtsReference -> value
            is EtsCast -> storage(value.value)
            else -> null
        }
        return returnedValue(function)?.let(::storage)?.symbol?.id?.startsWith("global:") == true
    }
    val valueFunctions = program.files.flatMap { it.declarations }.filterIsInstance<EtsFunction>()
        .filter { !it.builder && (it.body.singleOrNull() is EtsReturn || initializedTopLevelGetter(it)) }
        .associateBy { it.symbol.id }
    val valueParameters = mutableSetOf<String>()
    val checkingFunctions = mutableSetOf<String>()
    val constants = program.files.flatMap { it.declarations }.filterIsInstance<EtsGlobal>()
        .filter { !it.mutable }.map { it.symbol.id }.toSet()
    // Binding getters may run zero or many times. A single source reference does
    // not make calls or allocations safe to defer across a composition boundary.
    fun repeatable(value: EtsExpression): Boolean {
        return when (value) {
        is EtsLiteral, is EtsUndefined, is EtsLambda -> true
        is EtsReference -> value.symbol.id in parameters || value.symbol.id in reactiveInputs ||
            value.symbol.id in valueParameters || value.symbol.id in constants
        is EtsMember -> {
            val field = fields[(value.receiver.type as? EtsNamedType)?.symbolId to value.name]
            val native = (value.receiver as? EtsReference)?.symbol
            val enum = (value.type as? EtsNamedType)?.name
            val constant = enum in setOf("ImageFit", "Alignment", "HorizontalAlign", "VerticalAlign", "FlexAlign",
                "TextAlign", "TextOverflow", "TextDecorationType", "FontStyle", "ButtonType", "HitTestMode", "ScrollDirection") &&
                native?.external == true && native.id == "arkui:$enum" && native.type == value.type
            if (constant) true
            else if (value.symbolId == "arkui:Resource.id") repeatable(value.receiver)
            else if ((value.receiver.type as? EtsNamedType)?.name == "Binding" && value.name == "value") repeatable(value.receiver)
            else field != null && (field.state || field.prop || field.readonly) &&
                ((value.receiver as? EtsReference)?.symbol?.name == "this" || repeatable(value.receiver))
        }
        is EtsBinary -> repeatable(value.left) && repeatable(value.right)
        is EtsUnary -> repeatable(value.operand)
        is EtsConditional -> repeatable(value.condition) && repeatable(value.whenTrue) && repeatable(value.whenFalse)
        is EtsCast -> repeatable(value.value)
        is EtsNew -> (value.repeatableSnapshot || value.classType.symbolId in snapshots) && value.arguments.all(::repeatable)
        is EtsObject -> value.fields.values.all(::repeatable)
        is EtsCall -> {
            val immediate = value.callee as? EtsLambda
            if (immediate != null) {
                if (immediate.parameters.size != value.arguments.size || !value.arguments.all(::repeatable)) return false
                val scoped = mutableListOf<String>()
                fun bind(id: String) {
                    valueParameters += id
                    scoped += id
                }
                fun deterministicFailure(value: EtsExpression): Boolean =
                    value is EtsNew && value.classType == targetErrorType && value.arguments.all(::repeatable)
                fun guardStatement(statement: EtsStatement): Boolean = when (statement) {
                    is EtsThrow -> deterministicFailure(statement.value)
                    is EtsBlock -> statement.statements.all(::guardStatement)
                    is EtsIf -> statement.branches.all { branch ->
                        branch.condition?.let(::repeatable) != false && branch.body.all(::guardStatement)
                    }
                    else -> false
                }
                immediate.parameters.forEach { bind(it.symbol.id) }
                try {
                    var returned = false
                    immediate.body.forEachIndexed { index, statement -> when (statement) {
                        is EtsVariable -> {
                            val initializer = statement.initializer
                            // A compiler temporary may be declared mutable even when this
                            // closed IIFE never writes it. Any actual assignment is rejected
                            // by the statement whitelist below.
                            if (initializer == null || !repeatable(initializer)) return false
                            bind(statement.symbol.id)
                        }
                        is EtsIf -> if (!guardStatement(statement)) return false
                        is EtsReturn -> {
                            if (index != immediate.body.lastIndex || statement.value?.let(::repeatable) != true) return false
                            returned = true
                        }
                        else -> return false
                    } }
                    return returned
                } finally {
                    valueParameters.removeAll(scoped.toSet())
                }
            }
            val member = value.callee as? EtsMember
            val math = (member?.receiver as? EtsReference)?.symbol?.id == "stdlib:Math" &&
                member?.name in setOf("trunc", "min", "max", "fround")
            val functionId = (value.callee as? EtsReference)?.symbol?.id
            val function = valueFunctions[functionId]
            val manager = member?.receiver as? EtsMember
            val context = manager?.receiver as? EtsCall
            val resourceRead = member?.symbolId == "arkui:ResourceManager.getStringSync" &&
                manager?.name == "resourceManager" && (context?.callee as? EtsReference)?.symbol?.id == "arkui:getContext" &&
                context.arguments.isEmpty()
            if (functionId == "arkui:resource" || math || resourceRead) value.arguments.all(::repeatable)
            else if (function != null && function.parameters.size == value.arguments.size &&
                value.arguments.all(::repeatable) && checkingFunctions.add(function.symbol.id)) {
                val ids = function.parameters.map { it.symbol.id }
                valueParameters.addAll(ids)
                try {
                    initializedTopLevelGetter(function) || returnedValue(function)?.let(::repeatable) == true
                } finally {
                    valueParameters.removeAll(ids.toSet())
                    checkingFunctions.remove(function.symbol.id)
                }
            } else false
        }
            else -> false
        }
    }
    fun stableIdentity(value: EtsExpression): Boolean =
        value is EtsNew && value.stableIdentity && value.arguments.all(::repeatable)
    program.files.forEach { file -> file.declarations.forEach { declaration -> walkEts(declaration) { node ->
        if (node is EtsCall) {
            val parameters = builders[id(node)]?.parameters.orEmpty()
            if (parameters.any { it.symbol.id in bound }) node.arguments.forEachIndexed { index, argument ->
                val reactive = parameters[index].symbol.id in bound
                if (!repeatable(argument) && (reactive || !stableIdentity(argument))) throw Unsupported(Diagnostic("UNSUPPORTED",
                    "Reactive builder arguments require repeatable values; calls, allocations and mutable reads need an evaluation-preserving composition boundary: " +
                        "${parameters[index].symbol.name} (${argument::class.simpleName}, reactive=$reactive)", argument.source))
            }
        }
    } } }
    // Calls were proven repeatable above before becoming Binding getters. Reading
    // such a Binding from a loop or callback is what preserves current UI state;
    // only multiple immediate consumers still change source evaluation count.
    val bindingSnapshots = linkedMapOf<String, EtsSymbol>()
    builders.values.forEach { builder -> builder.parameters.filter { it.symbol.id in bound }.forEach { parameter ->
        var reads = 0
        builder.body.forEach { statement -> walkEts(statement) { node ->
            if (node is EtsReference && node.symbol.id == parameter.symbol.id) reads++
        } }
        // Native builder inputs are immutable snapshots for one update. Their
        // repeatable projections may feed several immediate UI attributes.
        if (reads > 1 && parameter.symbol.id !in nativeBound) bindingSnapshots[parameter.symbol.id] = EtsSymbol(
            "${parameter.symbol.id}:snapshot", "__ets_${parameter.symbol.name}", parameter.symbol.type,
            parameter.symbol.source)
    } }
    val rewrite = ReactiveBuilderRewriter(builders, bound, bindingSnapshots)
    return program.copy(files = program.files.map { it.copy(declarations = it.declarations.map(rewrite::declaration)) },
        imports = (program.imports + listOf(EtsImport("@kit.ArkUI", "Binding"), EtsImport("@kit.ArkUI", "UIUtils"))).distinct())
}

/** Only adapter-declared value descriptors may lose allocation identity. Verify
 * that construction merely stores arguments in readonly instance fields. */
private fun snapshotConstructor(owner: EtsClass): Boolean {
    if (owner.baseClass != null || owner.component) return false
    val fields = owner.members.filterIsInstance<EtsField>()
    if (fields.any { !it.readonly || it.static || it.initializer != null }) return false
    val constructor = owner.members.filterIsInstance<EtsFunction>().singleOrNull { it.kind == EtsFunctionKind.CONSTRUCTOR } ?: return false
    if (constructor.parameters.any { it.defaultValue != null } || constructor.body.size != fields.size) return false
    val assigned = mutableSetOf<String>()
    return constructor.body.all { statement ->
        val write = (statement as? EtsExpressionStatement)?.expression as? EtsAssignment ?: return@all false
        val field = write.target as? EtsMember ?: return@all false
        val receiver = field.receiver as? EtsReference ?: return@all false
        val value = write.value as? EtsReference ?: return@all false
        receiver.symbol.name == "this" && receiver.type == owner.symbol.type &&
            field.name in fields.map { it.symbol.name } && assigned.add(field.name) &&
            value.symbol.id in constructor.parameters.map { it.symbol.id }
    }
}

private class ReactiveBuilderRewriter(private val builders: Map<String, EtsFunction>,
    private val bound: Map<String, EtsParameter>, private val snapshots: Map<String, EtsSymbol>) {
    private fun binding(type: EtsType) = EtsNamedType("Binding", listOf(type), external = true)
    private fun parameter(value: EtsParameter) = if (value.symbol.id in bound)
        value.copy(symbol = value.symbol.copy(type = binding(value.symbol.type)), defaultValue = null) else value
    private fun functionType(value: EtsFunction) = EtsFunctionType(value.parameters.map { parameter(it).symbol.type }, value.returnType, value.typeParameters)
    private fun assignmentTarget(value: EtsExpression, locals: Map<String, EtsSymbol>): EtsExpression =
        if (value is EtsReference && value.symbol.id in bound) {
            val input = parameter(bound.getValue(value.symbol.id))
            EtsMember(EtsReference(input.symbol, value.source), "value", value.type, value.source)
        } else expression(value, locals)
    private fun expression(value: EtsExpression, locals: Map<String, EtsSymbol> = emptyMap()): EtsExpression = when (value) {
        is EtsReference -> if (value.symbol.id in locals) EtsReference(locals.getValue(value.symbol.id), value.source)
            else if (value.symbol.id in bound) EtsMember(
            EtsReference(parameter(bound.getValue(value.symbol.id)).symbol, value.source), "value", value.type, value.source)
            else builders[value.symbol.id]?.let { value.copy(symbol = value.symbol.copy(type = functionType(it))) } ?: value
        is EtsMember -> value.copy(receiver = expression(value.receiver, locals), type = builders[value.symbolId]?.let(::functionType) ?: value.type)
        is EtsCall -> {
            val id = when (val callee = value.callee) { is EtsReference -> callee.symbol.id; is EtsMember -> callee.symbolId; else -> null }
            val builder = builders[id]
            value.copy(callee = expression(value.callee, locals), arguments = value.arguments.mapIndexed { index, argument ->
                val emitted = expression(argument, locals)
                if (builder?.parameters?.getOrNull(index)?.symbol?.id !in bound) emitted else {
                    val lambda = EtsLambda(emptyList(), listOf(EtsReturn(emitted, argument.source)), emitted.type, argument.source)
                    val target = EtsReference(EtsSymbol("arkui:UIUtils", "UIUtils", EtsNamedType("UIUtils", external = true), argument.source, true))
                    EtsCall(EtsMember(target, "makeBinding", EtsFunctionType(listOf(lambda.type), binding(emitted.type)), argument.source),
                        listOf(lambda), binding(emitted.type), argument.source)
                }
            })
        }
        is EtsNew -> value.copy(arguments = value.arguments.map { expression(it, locals) })
        is EtsBinary -> value.copy(left = expression(value.left, locals), right = expression(value.right, locals))
        is EtsUnary -> value.copy(operand = expression(value.operand, locals))
        is EtsConditional -> value.copy(condition = expression(value.condition, locals),
            whenTrue = expression(value.whenTrue, locals), whenFalse = expression(value.whenFalse, locals))
        is EtsAssignment -> value.copy(target = assignmentTarget(value.target, locals), value = expression(value.value, locals))
        is EtsCast -> value.copy(value = expression(value.value, locals))
        is EtsArray -> value.copy(elements = value.elements.map { expression(it, locals) })
        is EtsObject -> value.copy(fields = value.fields.mapValues { expression(it.value, locals) })
        is EtsLambda -> value.copy(body = value.body.map { statement(it, locals) })
        is EtsSuper, is EtsLiteral, is EtsUndefined -> value
    }
    private fun function(value: EtsFunction): EtsFunction {
        val captured = value.parameters.mapNotNull { original -> snapshots[original.symbol.id]?.let { snapshot ->
            Triple(original, parameter(original), snapshot)
        } }
        val locals = captured.associate { (original, _, snapshot) -> original.symbol.id to snapshot }
        var body = value.body.map { statement(it, locals) }
        captured.asReversed().forEach { (original, input, snapshot) ->
            val read = EtsMember(EtsReference(input.symbol, original.symbol.source), "value",
                original.symbol.type, original.symbol.source)
            body = listOf(EtsUiForEach(EtsArray(listOf(read), original.symbol.type, original.symbol.source),
                EtsParameter(snapshot), body, original.symbol.source))
        }
        return value.copy(parameters = value.parameters.map(::parameter), body = body)
    }
    fun declaration(value: EtsDeclaration): EtsDeclaration = when (value) {
        is EtsFunction -> function(value)
        is EtsGlobal -> value.copy(initializer = expression(value.initializer))
        is EtsClass -> value.copy(members = value.members.map { when (it) {
            is EtsFunction -> function(it)
            is EtsField -> it.copy(initializer = it.initializer?.let(::expression))
        } })
    }
    private fun statement(value: EtsStatement, locals: Map<String, EtsSymbol> = emptyMap()): EtsStatement = when (value) {
        is EtsVariable -> value.copy(initializer = value.initializer?.let { expression(it, locals) })
        is EtsExpressionStatement -> value.copy(expression = expression(value.expression, locals))
        is EtsReturn -> value.copy(value = value.value?.let { expression(it, locals) })
        is EtsThrow -> value.copy(value = expression(value.value, locals))
        is EtsTry -> value.copy(body = value.body.map { statement(it, locals) },
            handler = value.handler?.let { it.copy(body = it.body.map { body -> statement(body, locals) }) },
            finallyBody = value.finallyBody?.map { statement(it, locals) })
        is EtsSuperConstructorCall -> value.copy(arguments = value.arguments.map { expression(it, locals) })
        is EtsBlock -> value.copy(statements = value.statements.map { statement(it, locals) })
        is EtsIf -> value.copy(branches = value.branches.map { branch -> branch.copy(
            condition = branch.condition?.let { expression(it, locals) },
            body = branch.body.map { statement(it, locals) }) })
        is EtsLoop -> value.copy(condition = expression(value.condition, locals), body = value.body.map { statement(it, locals) })
        is EtsUiElement -> value.copy(call = expression(value.call, locals) as EtsCall,
            children = value.children?.map { statement(it, locals) },
            attributes = value.attributes.map { expression(it, locals) as EtsCall })
        is EtsUiComponent -> value.copy(properties = value.properties.mapValues { expression(it.value, locals) })
        is EtsUiForEach -> value.copy(items = expression(value.items, locals), body = value.body.map { statement(it, locals) },
            key = value.key?.let { expression(it, locals) } as? EtsLambda)
        is EtsUiLazyForEach -> value.copy(dataSource = expression(value.dataSource, locals),
            body = value.body.map { statement(it, locals) }, key = value.key?.let { expression(it, locals) } as? EtsLambda)
        is EtsFunction -> function(value)
        is EtsJump -> value
    }
}
