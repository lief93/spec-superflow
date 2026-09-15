package dev.ets

/** ArkUI value parameters freeze outside an observed element. Use the SDK's
 * Binding contract for single-consumer state-dependent builder argument chains. */
internal fun bindReactiveBuilderArguments(program: EtsProgram): EtsProgram {
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
    fun dependent(value: EtsExpression): Boolean {
        var result = false
        walkEts(value) {
            if (it is EtsReference && it.symbol.id in bound) result = true
            if (it is EtsMember && (it.receiver.type as? EtsNamedType)?.symbolId to it.name in states) result = true
        }
        return result
    }
    do {
        val count = bound.size
        program.files.forEach { file -> file.declarations.forEach { declaration -> walkEts(declaration) { node ->
            if (node is EtsUiElement) builders[id(node.call)]?.parameters?.zip(node.call.arguments)?.forEach { (parameter, argument) ->
                if (parameter.symbol.type !is EtsFunctionType && dependent(argument)) bound[parameter.symbol.id] = parameter
            }
        } } }
    } while (count != bound.size)
    if (bound.isEmpty()) return program
    val parameters = builders.values.flatMap { it.parameters }.map { it.symbol.id }.toSet()
    val fields = program.files.flatMap { it.declarations }.filterIsInstance<EtsClass>().flatMap { owner ->
        owner.members.filterIsInstance<EtsField>().map { (owner.symbol.id to it.symbol.name) to it }
    }.toMap()
    // Binding getters may run zero or many times. A single source reference does
    // not make calls or allocations safe to defer across a composition boundary.
    fun repeatable(value: EtsExpression): Boolean = when (value) {
        is EtsLiteral, is EtsUndefined, is EtsLambda -> true
        is EtsReference -> value.symbol.id in parameters
        is EtsMember -> {
            val field = fields[(value.receiver.type as? EtsNamedType)?.symbolId to value.name]
            field != null && (field.state || field.prop || field.readonly) &&
                ((value.receiver as? EtsReference)?.symbol?.name == "this" || repeatable(value.receiver))
        }
        is EtsBinary -> repeatable(value.left) && repeatable(value.right)
        is EtsUnary -> repeatable(value.operand)
        is EtsConditional -> repeatable(value.condition) && repeatable(value.whenTrue) && repeatable(value.whenFalse)
        is EtsCast -> repeatable(value.value)
        is EtsCall -> (value.callee as? EtsReference)?.symbol?.id == "arkui:resource" && value.arguments.all(::repeatable)
        else -> false
    }
    program.files.forEach { file -> file.declarations.forEach { declaration -> walkEts(declaration) { node ->
        if (node is EtsUiElement) {
            val parameters = builders[id(node.call)]?.parameters.orEmpty()
            if (parameters.any { it.symbol.id in bound }) node.call.arguments.forEach { argument ->
                if (!repeatable(argument)) throw Unsupported(Diagnostic("UNSUPPORTED",
                    "Reactive builder arguments require repeatable values; calls, allocations and mutable reads need an evaluation-preserving composition boundary", argument.source))
            }
        }
    } } }
    // Do not turn a once-evaluated source argument into multiple lazy executions.
    builders.values.forEach { builder -> builder.parameters.filter { it.symbol.id in bound }.forEach { parameter ->
        var reads = 0
        var repeated = false
        builder.body.forEach { statement -> walkEts(statement) { node ->
            if (node is EtsReference && node.symbol.id == parameter.symbol.id) reads++
            val delayed = when (node) {
                is EtsUiForEach -> node.body
                is EtsLoop -> node.body
                is EtsLambda -> node.body
                else -> emptyList()
            }
            delayed.forEach { body -> walkEts(body) { if (it is EtsReference && it.symbol.id == parameter.symbol.id) repeated = true } }
        } }
        if (reads != 1 || repeated) throw Unsupported(Diagnostic("UNSUPPORTED",
            "Reactive builder parameter requires a single immediate consumer; shared/repeated evaluation needs a composition boundary: ${parameter.symbol.name}", parameter.symbol.source))
    } }
    val rewrite = ReactiveBuilderRewriter(builders, bound)
    return program.copy(files = program.files.map { it.copy(declarations = it.declarations.map(rewrite::declaration)) },
        imports = (program.imports + listOf(EtsImport("@kit.ArkUI", "Binding"), EtsImport("@kit.ArkUI", "UIUtils"))).distinct())
}

private class ReactiveBuilderRewriter(private val builders: Map<String, EtsFunction>, private val bound: Map<String, EtsParameter>) {
    private fun binding(type: EtsType) = EtsNamedType("Binding", listOf(type), external = true)
    private fun parameter(value: EtsParameter) = if (value.symbol.id in bound)
        value.copy(symbol = value.symbol.copy(type = binding(value.symbol.type)), defaultValue = null) else value
    private fun functionType(value: EtsFunction) = EtsFunctionType(value.parameters.map { parameter(it).symbol.type }, value.returnType, value.typeParameters)
    private fun expression(value: EtsExpression): EtsExpression = when (value) {
        is EtsReference -> if (value.symbol.id in bound) EtsMember(
            EtsReference(parameter(bound.getValue(value.symbol.id)).symbol, value.source), "value", value.type, value.source)
            else builders[value.symbol.id]?.let { value.copy(symbol = value.symbol.copy(type = functionType(it))) } ?: value
        is EtsMember -> value.copy(receiver = expression(value.receiver), type = builders[value.symbolId]?.let(::functionType) ?: value.type)
        is EtsCall -> {
            val id = when (val callee = value.callee) { is EtsReference -> callee.symbol.id; is EtsMember -> callee.symbolId; else -> null }
            val builder = builders[id]
            value.copy(callee = expression(value.callee), arguments = value.arguments.mapIndexed { index, argument ->
                val emitted = expression(argument)
                if (builder?.parameters?.getOrNull(index)?.symbol?.id !in bound) emitted else {
                    val lambda = EtsLambda(emptyList(), listOf(EtsReturn(emitted, argument.source)), emitted.type, argument.source)
                    val target = EtsReference(EtsSymbol("arkui:UIUtils", "UIUtils", EtsNamedType("UIUtils", external = true), argument.source, true))
                    EtsCall(EtsMember(target, "makeBinding", EtsFunctionType(listOf(lambda.type), binding(emitted.type)), argument.source),
                        listOf(lambda), binding(emitted.type), argument.source)
                }
            })
        }
        is EtsNew -> value.copy(arguments = value.arguments.map(::expression))
        is EtsBinary -> value.copy(left = expression(value.left), right = expression(value.right))
        is EtsUnary -> value.copy(operand = expression(value.operand))
        is EtsConditional -> value.copy(condition = expression(value.condition), whenTrue = expression(value.whenTrue), whenFalse = expression(value.whenFalse))
        is EtsAssignment -> value.copy(target = expression(value.target), value = expression(value.value))
        is EtsCast -> value.copy(value = expression(value.value))
        is EtsArray -> value.copy(elements = value.elements.map(::expression))
        is EtsObject -> value.copy(fields = value.fields.mapValues { expression(it.value) })
        is EtsLambda -> value.copy(body = value.body.map(::statement))
        is EtsSuper, is EtsLiteral, is EtsUndefined -> value
    }
    private fun function(value: EtsFunction) = value.copy(parameters = value.parameters.map(::parameter), body = value.body.map(::statement))
    fun declaration(value: EtsDeclaration): EtsDeclaration = when (value) {
        is EtsFunction -> function(value)
        is EtsGlobal -> value.copy(initializer = expression(value.initializer))
        is EtsClass -> value.copy(members = value.members.map { when (it) {
            is EtsFunction -> function(it)
            is EtsField -> it.copy(initializer = it.initializer?.let(::expression))
        } })
    }
    private fun statement(value: EtsStatement): EtsStatement = when (value) {
        is EtsVariable -> value.copy(initializer = value.initializer?.let(::expression))
        is EtsExpressionStatement -> value.copy(expression = expression(value.expression))
        is EtsReturn -> value.copy(value = value.value?.let(::expression))
        is EtsThrow -> value.copy(value = expression(value.value))
        is EtsTry -> value.copy(body = value.body.map(::statement), handler = value.handler?.let { it.copy(body = it.body.map(::statement)) }, finallyBody = value.finallyBody?.map(::statement))
        is EtsSuperConstructorCall -> value.copy(arguments = value.arguments.map(::expression))
        is EtsBlock -> value.copy(statements = value.statements.map(::statement))
        is EtsIf -> value.copy(branches = value.branches.map { it.copy(condition = it.condition?.let(::expression), body = it.body.map(::statement)) })
        is EtsLoop -> value.copy(condition = expression(value.condition), body = value.body.map(::statement))
        is EtsUiElement -> value.copy(call = expression(value.call) as EtsCall, children = value.children?.map(::statement), attributes = value.attributes.map { expression(it) as EtsCall })
        is EtsUiComponent -> value.copy(properties = value.properties.mapValues { expression(it.value) })
        is EtsUiForEach -> value.copy(items = expression(value.items), body = value.body.map(::statement))
        is EtsFunction -> function(value)
        is EtsJump -> value
    }
}
