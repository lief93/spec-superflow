package dev.ets

/** Source builder edges may lose their receiver; actual page and generated bridge uses may not. */
internal class BuilderOwnership(functions: List<EtsFunction>, rootId: String, private val receiverId: String) {
    private val symbols = functions.associate { it.symbol.id to it.symbol }
    val globalIds: Set<String>

    init {
        val page = mutableSetOf(rootId)
        val dependencies = linkedMapOf<String, Set<String>>()
        for (function in functions) {
            var sourceReceiverOccurrences = 0
            var pageOccurrences = 0
            val calls = mutableSetOf<String>()
            walkEts(function) { node ->
                // An ordinary callback retains its lexical page receiver. It is
                // not a native BuilderNode parameterized entry point.
                if (node is EtsLambda) walkEts(node) { nested ->
                    if (nested is EtsMember && nested.symbolId in symbols && isPage(nested.receiver)) page += nested.symbolId!!
                }
                if (node is EtsMember && node.symbolId in symbols && isPage(node.receiver)) {
                    sourceReceiverOccurrences++
                    calls += node.symbolId!!
                }
                if (node is EtsReference && isPage(node)) pageOccurrences++
            }
            // Count edges, not node identities: an immutable receiver can be shared with a real field read.
            if (pageOccurrences > sourceReceiverOccurrences) page += function.symbol.id
            dependencies[function.symbol.id] = calls
        }
        do {
            val changed = dependencies.filter { (id, calls) -> id !in page && calls.any { it in page } }.keys
            page += changed
        } while (changed.isNotEmpty())
        globalIds = symbols.keys - page
    }

    private fun isPage(expression: EtsExpression) = expression is EtsReference && expression.symbol.id == receiverId

    fun rewrite(function: EtsFunction): EtsFunction = function.copy(
        parameters = function.parameters.map(::parameter), body = function.body.map(::statement))

    private fun parameter(value: EtsParameter) = value.copy(defaultValue = value.defaultValue?.let(::expression))
    private fun expression(value: EtsExpression): EtsExpression = when (value) {
        is EtsReference, is EtsSuper, is EtsLiteral, is EtsUndefined -> value
        is EtsMember -> if (value.symbolId in globalIds && isPage(value.receiver))
            EtsReference(symbols.getValue(value.symbolId!!), value.source)
            else value.copy(receiver = expression(value.receiver))
        is EtsCall -> value.copy(callee = expression(value.callee), arguments = value.arguments.map(::expression))
        is EtsNew -> value.copy(arguments = value.arguments.map(::expression))
        is EtsBinary -> value.copy(left = expression(value.left), right = expression(value.right))
        is EtsUnary -> value.copy(operand = expression(value.operand))
        is EtsConditional -> value.copy(condition = expression(value.condition), whenTrue = expression(value.whenTrue), whenFalse = expression(value.whenFalse))
        is EtsAssignment -> value.copy(target = expression(value.target), value = expression(value.value))
        is EtsCast -> value.copy(value = expression(value.value))
        is EtsArray -> value.copy(elements = value.elements.map(::expression))
        is EtsObject -> value.copy(fields = value.fields.mapValues { expression(it.value) })
        is EtsLambda -> value.copy(parameters = value.parameters.map(::parameter), body = value.body.map(::statement))
    }

    private fun statement(value: EtsStatement): EtsStatement = when (value) {
        is EtsVariable -> value.copy(initializer = value.initializer?.let(::expression))
        is EtsExpressionStatement -> value.copy(expression = expression(value.expression))
        is EtsReturn -> value.copy(value = value.value?.let(::expression))
        is EtsThrow -> value.copy(value = expression(value.value))
        is EtsTry -> value.copy(body = value.body.map(::statement),
            handler = value.handler?.let { it.copy(body = it.body.map(::statement)) },
            finallyBody = value.finallyBody?.map(::statement))
        is EtsSuperConstructorCall -> value.copy(arguments = value.arguments.map(::expression))
        is EtsBlock -> value.copy(statements = value.statements.map(::statement))
        is EtsIf -> value.copy(branches = value.branches.map { it.copy(condition = it.condition?.let(::expression), body = it.body.map(::statement)) })
        is EtsLoop -> value.copy(condition = expression(value.condition), body = value.body.map(::statement))
        is EtsJump -> value
        is EtsUiElement -> value.copy(call = expression(value.call) as EtsCall, children = value.children?.map(::statement), attributes = value.attributes.map { expression(it) as EtsCall })
        is EtsUiComponent -> value.copy(properties = value.properties.mapValues { expression(it.value) })
        is EtsUiForEach -> value.copy(items = expression(value.items), item = parameter(value.item), body = value.body.map(::statement))
        is EtsFunction -> rewrite(value)
    }
}
