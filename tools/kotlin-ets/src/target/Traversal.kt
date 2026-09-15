package dev.ets

/** Visit emitted nodes, including defaults and nested bodies, in structural order. */
fun walkEts(node: EtsNode, visit: (EtsNode) -> Unit) {
    visit(node)
    fun walk(child: EtsNode) = walkEts(child, visit)
    fun parameters(values: List<EtsParameter>) = values.forEach { it.defaultValue?.let(::walk) }
    when (node) {
        is EtsReference, is EtsSuper, is EtsLiteral, is EtsUndefined, is EtsJump -> Unit
        is EtsMember -> walk(node.receiver)
        is EtsCall -> { walk(node.callee); node.arguments.forEach(::walk) }
        is EtsNew -> node.arguments.forEach(::walk)
        is EtsBinary -> { walk(node.left); walk(node.right) }
        is EtsUnary -> walk(node.operand)
        is EtsConditional -> { walk(node.condition); walk(node.whenTrue); walk(node.whenFalse) }
        is EtsAssignment -> { walk(node.target); walk(node.value) }
        is EtsCast -> walk(node.value)
        is EtsArray -> node.elements.forEach(::walk)
        is EtsObject -> node.fields.values.forEach(::walk)
        is EtsLambda -> { parameters(node.parameters); node.body.forEach(::walk) }
        is EtsVariable -> node.initializer?.let(::walk)
        is EtsGlobal -> walk(node.initializer)
        is EtsExpressionStatement -> walk(node.expression)
        is EtsReturn -> node.value?.let(::walk)
        is EtsThrow -> walk(node.value)
        is EtsTry -> { node.body.forEach(::walk); node.handler?.body?.forEach(::walk); node.finallyBody?.forEach(::walk) }
        is EtsSuperConstructorCall -> node.arguments.forEach(::walk)
        is EtsBlock -> node.statements.forEach(::walk)
        is EtsIf -> node.branches.forEach { branch ->
            branch.condition?.let(::walk)
            branch.body.forEach(::walk)
        }
        is EtsLoop -> { walk(node.condition); node.body.forEach(::walk) }
        is EtsUiElement -> { walk(node.call); node.children?.forEach(::walk); node.attributes.forEach(::walk) }
        is EtsUiComponent -> { walk(node.component); node.properties.values.forEach(::walk) }
        is EtsUiForEach -> { walk(node.items); parameters(listOf(node.item)); node.body.forEach(::walk) }
        is EtsFunction -> { parameters(node.parameters); node.body.forEach(::walk) }
        is EtsField -> node.initializer?.let(::walk)
        is EtsClass -> node.members.forEach(::walk)
    }
}
