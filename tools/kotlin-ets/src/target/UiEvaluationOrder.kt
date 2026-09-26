package dev.ets

private fun combineEvaluation(values: Iterable<EtsEvaluationSemantics>,
    createsIdentity: Boolean = false): EtsEvaluationSemantics {
    val items = values.toList()
    val effect = when {
        items.any { it.effect == EtsObservableEffect.UNKNOWN } -> EtsObservableEffect.UNKNOWN
        items.any { it.effect == EtsObservableEffect.WRITES_RUNTIME } -> EtsObservableEffect.WRITES_RUNTIME
        items.any { it.effect == EtsObservableEffect.READS_RUNTIME } -> EtsObservableEffect.READS_RUNTIME
        else -> EtsObservableEffect.NONE
    }
    return EtsEvaluationSemantics(effect,
        createsIdentity || items.any(EtsEvaluationSemantics::createsIdentity),
        items.any(EtsEvaluationSemantics::mayThrow))
}

/** Conservative facts available before target declarations have been linked. */
fun staticTargetEvaluation(value: EtsExpression): EtsEvaluationSemantics = when (value) {
    is EtsLiteral, is EtsUndefined, is EtsSuper ->
        EtsEvaluationSemantics(EtsObservableEffect.NONE)
    is EtsReference -> value.symbol.evaluation
    is EtsLambda -> EtsEvaluationSemantics(EtsObservableEffect.NONE, createsIdentity = true)
    is EtsMember -> combineEvaluation(listOf(staticTargetEvaluation(value.receiver), value.evaluation))
    is EtsCall -> combineEvaluation(value.arguments.map(::staticTargetEvaluation) +
        staticTargetEvaluation(value.callee) + EtsEvaluationSemantics(EtsObservableEffect.UNKNOWN))
    is EtsNew -> combineEvaluation(value.arguments.map(::staticTargetEvaluation) +
        EtsEvaluationSemantics(EtsObservableEffect.UNKNOWN), createsIdentity = true)
    is EtsBinary -> combineEvaluation(listOf(staticTargetEvaluation(value.left),
        staticTargetEvaluation(value.right)))
    is EtsUnary -> staticTargetEvaluation(value.operand)
    is EtsConditional -> combineEvaluation(listOf(staticTargetEvaluation(value.condition),
        staticTargetEvaluation(value.whenTrue), staticTargetEvaluation(value.whenFalse)))
    is EtsAssignment -> combineEvaluation(listOf(staticTargetEvaluation(value.target),
        staticTargetEvaluation(value.value), EtsEvaluationSemantics(EtsObservableEffect.WRITES_RUNTIME)))
    is EtsCast -> staticTargetEvaluation(value.value)
    is EtsArray -> combineEvaluation(value.elements.map(::staticTargetEvaluation), createsIdentity = true)
    is EtsObject -> combineEvaluation(value.fields.values.map(::staticTargetEvaluation), createsIdentity = true)
}

/**
 * Remove source-order bindings when the complete linked target program proves
 * that every value in the binding chain is side-effect free. The Harmony
 * backend creates conservative bindings before all source and support
 * declarations are available; this target phase is the single place that may
 * discharge them.
 */
fun simplifyPureUiEvaluationBindings(program: EtsProgram): EtsProgram {
    val functions = linkedMapOf<String, EtsFunction>()
    val classes = linkedMapOf<String, EtsClass>()
    program.files.forEach { file -> file.declarations.forEach { declaration ->
        when (declaration) {
            is EtsFunction -> functions[declaration.symbol.id] = declaration
            is EtsClass -> {
                classes[declaration.symbol.id] = declaration
                declaration.members.filterIsInstance<EtsFunction>().forEach { functions[it.symbol.id] = it }
            }
            is EtsGlobal -> Unit
        }
    } }

    val pureFunctions = mutableSetOf<String>()
    val pureClasses = mutableSetOf<String>()

    fun pureExpression(value: EtsExpression): Boolean {
        if (staticTargetEvaluation(value).canReorder) return true
        return when (value) {
        is EtsLiteral, is EtsUndefined, is EtsSuper, is EtsLambda -> true
        is EtsReference -> value.symbol.evaluation.canReorder
        // A member can be implemented by a getter or read mutable runtime state.
        is EtsMember -> false
        is EtsCall -> {
            val member = value.callee as? EtsMember
            val receiver = member?.receiver as? EtsReference
            val intrinsic = receiver?.symbol?.id == "stdlib:Math" &&
                member.name in setOf("trunc", "min", "max", "fround")
            val id = when (val callee = value.callee) {
                is EtsReference -> callee.symbol.id
                is EtsMember -> callee.symbolId
                else -> null
            }
            (intrinsic || id in pureFunctions) && value.arguments.all(::pureExpression)
        }
        is EtsNew -> value.classType.symbolId in pureClasses && value.arguments.all(::pureExpression)
        is EtsBinary -> pureExpression(value.left) && pureExpression(value.right)
        is EtsUnary -> pureExpression(value.operand)
        is EtsConditional -> pureExpression(value.condition) && pureExpression(value.whenTrue) &&
            pureExpression(value.whenFalse)
        is EtsCast -> pureExpression(value.value)
        is EtsArray -> value.elements.all(::pureExpression)
        is EtsObject -> value.fields.values.all(::pureExpression)
        is EtsAssignment -> false
    } }

    fun pureStatement(value: EtsStatement): Boolean = when (value) {
        is EtsVariable -> !value.mutable && value.initializer?.let(::pureExpression) != false
        is EtsExpressionStatement -> pureExpression(value.expression)
        is EtsReturn -> value.value?.let(::pureExpression) != false
        is EtsBlock -> value.statements.all(::pureStatement)
        is EtsIf -> value.branches.all { branch ->
            branch.condition?.let(::pureExpression) != false && branch.body.all(::pureStatement)
        }
        is EtsFunction -> value.body.all(::pureStatement)
        is EtsThrow, is EtsTry, is EtsSuperConstructorCall, is EtsLoop, is EtsJump,
        is EtsUiElement, is EtsUiComponent, is EtsUiForEach, is EtsUiLazyForEach -> false
    }

    fun pureConstructor(owner: EtsClass): Boolean {
        if (owner.baseClass != null || owner.component) return false
        val constructor = owner.members.filterIsInstance<EtsFunction>()
            .singleOrNull { it.kind == EtsFunctionKind.CONSTRUCTOR } ?: return true
        return constructor.body.all { statement ->
            val assignment = (statement as? EtsExpressionStatement)?.expression as? EtsAssignment
                ?: return@all false
            val member = assignment.target as? EtsMember ?: return@all false
            val receiver = member.receiver as? EtsReference ?: return@all false
            receiver.symbol.name == "this" && pureExpression(assignment.value)
        }
    }

    do {
        val previous = pureFunctions.size + pureClasses.size
        classes.values.filter(::pureConstructor).mapTo(pureClasses) { it.symbol.id }
        functions.values.filter {
            it.kind != EtsFunctionKind.CONSTRUCTOR && !it.builder && !it.build &&
                it.body.all(::pureStatement)
        }.mapTo(pureFunctions) { it.symbol.id }
    } while (previous != pureFunctions.size + pureClasses.size)

    lateinit var rewriteStatement: (EtsStatement, Map<String, EtsExpression>) -> EtsStatement
    lateinit var rewriteStatements: (List<EtsStatement>, Map<String, EtsExpression>) -> List<EtsStatement>
    fun expression(value: EtsExpression, bindings: Map<String, EtsExpression>): EtsExpression = when (value) {
        is EtsReference -> bindings[value.symbol.id] ?: value
        is EtsMember -> value.copy(receiver = expression(value.receiver, bindings))
        is EtsCall -> value.copy(callee = expression(value.callee, bindings),
            arguments = value.arguments.map { expression(it, bindings) })
        is EtsNew -> value.copy(arguments = value.arguments.map { expression(it, bindings) })
        is EtsBinary -> value.copy(left = expression(value.left, bindings), right = expression(value.right, bindings))
        is EtsUnary -> value.copy(operand = expression(value.operand, bindings))
        is EtsConditional -> value.copy(condition = expression(value.condition, bindings),
            whenTrue = expression(value.whenTrue, bindings), whenFalse = expression(value.whenFalse, bindings))
        is EtsAssignment -> value.copy(target = expression(value.target, bindings),
            value = expression(value.value, bindings))
        is EtsCast -> value.copy(value = expression(value.value, bindings))
        is EtsArray -> value.copy(elements = value.elements.map { expression(it, bindings) })
        is EtsObject -> value.copy(fields = value.fields.mapValues { expression(it.value, bindings) })
        is EtsLambda -> value.copy(body = value.body.flatMap { rewriteStatements(listOf(it), bindings) })
        is EtsLiteral, is EtsUndefined, is EtsSuper -> value
    }

    lateinit var expressionReferences: (EtsExpression, String) -> Int
    lateinit var statementReferences: (EtsStatement, String) -> Int
    expressionReferences = { value, symbolId -> when (value) {
        is EtsReference -> if (value.symbol.id == symbolId) 1 else 0
        is EtsMember -> expressionReferences(value.receiver, symbolId)
        is EtsCall -> expressionReferences(value.callee, symbolId) +
            value.arguments.sumOf { expressionReferences(it, symbolId) }
        is EtsNew -> value.arguments.sumOf { expressionReferences(it, symbolId) }
        is EtsBinary -> expressionReferences(value.left, symbolId) +
            expressionReferences(value.right, symbolId)
        is EtsUnary -> expressionReferences(value.operand, symbolId)
        is EtsConditional -> expressionReferences(value.condition, symbolId) +
            expressionReferences(value.whenTrue, symbolId) + expressionReferences(value.whenFalse, symbolId)
        is EtsAssignment -> expressionReferences(value.target, symbolId) +
            expressionReferences(value.value, symbolId)
        is EtsCast -> expressionReferences(value.value, symbolId)
        is EtsArray -> value.elements.sumOf { expressionReferences(it, symbolId) }
        is EtsObject -> value.fields.values.sumOf { expressionReferences(it, symbolId) }
        is EtsLambda -> value.body.sumOf { statementReferences(it, symbolId) }
        is EtsLiteral, is EtsUndefined, is EtsSuper -> 0
    } }

    statementReferences = { value, symbolId -> when (value) {
        is EtsVariable -> value.initializer?.let { expressionReferences(it, symbolId) } ?: 0
        is EtsExpressionStatement -> expressionReferences(value.expression, symbolId)
        is EtsReturn -> value.value?.let { expressionReferences(it, symbolId) } ?: 0
        is EtsThrow -> expressionReferences(value.value, symbolId)
        is EtsTry -> value.body.sumOf { statementReferences(it, symbolId) } +
            (value.handler?.body?.sumOf { statementReferences(it, symbolId) } ?: 0) +
            (value.finallyBody?.sumOf { statementReferences(it, symbolId) } ?: 0)
        is EtsSuperConstructorCall -> value.arguments.sumOf { expressionReferences(it, symbolId) }
        is EtsBlock -> value.statements.sumOf { statementReferences(it, symbolId) }
        is EtsIf -> value.branches.sumOf { branch ->
            (branch.condition?.let { expressionReferences(it, symbolId) } ?: 0) +
                branch.body.sumOf { statementReferences(it, symbolId) }
        }
        is EtsLoop -> expressionReferences(value.condition, symbolId) +
            value.body.sumOf { statementReferences(it, symbolId) }
        is EtsUiElement -> expressionReferences(value.call, symbolId) +
            value.attributes.sumOf { expressionReferences(it, symbolId) } +
            (value.children?.sumOf { statementReferences(it, symbolId) } ?: 0)
        is EtsUiComponent -> expressionReferences(value.component, symbolId) +
            value.properties.values.sumOf { expressionReferences(it, symbolId) }
        is EtsUiForEach -> expressionReferences(value.items, symbolId) +
            value.body.sumOf { statementReferences(it, symbolId) } +
            (value.key?.let { expressionReferences(it, symbolId) } ?: 0)
        is EtsUiLazyForEach -> expressionReferences(value.dataSource, symbolId) +
            value.body.sumOf { statementReferences(it, symbolId) } +
            (value.key?.let { expressionReferences(it, symbolId) } ?: 0)
        is EtsFunction -> value.body.sumOf { statementReferences(it, symbolId) }
        is EtsJump -> 0
    } }

    rewriteStatements = { values, bindings -> values.flatMap { value ->
            if (value is EtsUiForEach && value.kind == EtsUiForEachKind.SOURCE_EVALUATION) {
                val argument = (value.items as? EtsArray)?.elements?.singleOrNull()
                if (argument != null && value.key == null) {
                    val resolved = expression(argument, bindings)
                    val symbolId = value.item.symbol.id
                    val uses = value.body.sumOf { statementReferences(it, symbolId) }
                    if (pureExpression(resolved) &&
                        (uses <= 1 || staticTargetEvaluation(resolved).canDuplicate)) {
                        return@flatMap rewriteStatements(value.body, bindings + (symbolId to resolved))
                    }
                }
            }
            listOf(rewriteStatement(value, bindings))
        } }

    rewriteStatement = { value, bindings -> when (value) {
            is EtsVariable -> value.copy(initializer = value.initializer?.let { expression(it, bindings) })
            is EtsExpressionStatement -> value.copy(expression = expression(value.expression, bindings))
            is EtsReturn -> value.copy(value = value.value?.let { expression(it, bindings) })
            is EtsThrow -> value.copy(value = expression(value.value, bindings))
            is EtsTry -> value.copy(body = rewriteStatements(value.body, bindings),
                handler = value.handler?.let { it.copy(body = rewriteStatements(it.body, bindings)) },
                finallyBody = value.finallyBody?.let { rewriteStatements(it, bindings) })
            is EtsSuperConstructorCall -> value.copy(arguments = value.arguments.map { expression(it, bindings) })
            is EtsBlock -> value.copy(statements = rewriteStatements(value.statements, bindings))
            is EtsIf -> value.copy(branches = value.branches.map { branch -> branch.copy(
                condition = branch.condition?.let { expression(it, bindings) },
                body = rewriteStatements(branch.body, bindings)) })
            is EtsLoop -> value.copy(condition = expression(value.condition, bindings),
                body = rewriteStatements(value.body, bindings))
            is EtsUiElement -> value.copy(call = expression(value.call, bindings) as EtsCall,
                children = value.children?.let { rewriteStatements(it, bindings) },
                attributes = value.attributes.map { expression(it, bindings) as EtsCall })
            is EtsUiComponent -> value.copy(properties = value.properties.mapValues { expression(it.value, bindings) })
            is EtsUiForEach -> value.copy(items = expression(value.items, bindings),
                body = rewriteStatements(value.body, bindings),
                key = value.key?.let { expression(it, bindings) } as? EtsLambda)
            is EtsUiLazyForEach -> value.copy(dataSource = expression(value.dataSource, bindings),
                body = rewriteStatements(value.body, bindings),
                key = value.key?.let { expression(it, bindings) } as? EtsLambda)
            is EtsFunction -> value.copy(body = rewriteStatements(value.body, bindings))
            is EtsJump -> value
        } }

    fun declaration(value: EtsDeclaration): EtsDeclaration = when (value) {
        is EtsFunction -> value.copy(body = rewriteStatements(value.body, emptyMap()))
        is EtsGlobal -> value.copy(initializer = expression(value.initializer, emptyMap()))
        is EtsClass -> value.copy(members = value.members.map { member -> when (member) {
            is EtsFunction -> declaration(member) as EtsFunction
            is EtsField -> member.copy(initializer = member.initializer?.let { expression(it, emptyMap()) })
        } })
    }
    return program.copy(files = program.files.map { file ->
        file.copy(declarations = file.declarations.map(::declaration))
    })
}
