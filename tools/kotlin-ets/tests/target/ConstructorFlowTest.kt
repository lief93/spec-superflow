package dev.ets

private class ConstructorFlowFixture {
    val source = SourceSpan("ConstructorFlow.kt", 10, 100)
    val number = EtsTypes.NUMBER
    val mode = EtsParameter(EtsSymbol("mode", "mode", number, source))
    val seed = EtsParameter(EtsSymbol("seed", "seed", number, source))
    fun literal(value: Int) = EtsLiteral(value, number, source)
    fun add(value: EtsExpression, extra: Int) = EtsBinary("+", value, literal(extra), number, source)
    val baseShell = EtsClass("FlowBase", emptyList(), source.copy(start = 1))
    val childShell = EtsClass("FlowChild", emptyList(), source.copy(start = 2), baseClass = baseShell.symbol.type as EtsNamedType)
    val self = EtsReference(EtsSymbol("child:this", "this", childShell.symbol.type, source, external = true))
    fun store(receiver: EtsExpression, name: String, value: EtsExpression) =
        EtsExpressionStatement(EtsAssignment(EtsMember(receiver, name, number, source), value, source))
    val own = EtsMember(self, "own", number, source)
    val condition = EtsBinary("===", EtsReference(mode.symbol), literal(0), EtsTypes.BOOLEAN, source)
    val delegation = EtsSuperConstructorCall(baseShell.symbol.type as EtsNamedType, listOf(EtsReference(seed.symbol)), source)
    fun choice(first: List<EtsStatement>, second: List<EtsStatement>?) =
        EtsIf(listOf(EtsBranch(condition, first)) + listOfNotNull(second?.let { EtsBranch(null, it) }), source)
    val ctor = EtsFunction("constructor", listOf(mode, seed), EtsTypes.VOID, emptyList(), source.copy(start = 3),
        kind = EtsFunctionKind.CONSTRUCTOR)
    fun program(body: List<EtsStatement>, parameters: List<EtsParameter> = ctor.parameters): EtsProgram {
        val baseThis = EtsReference(EtsSymbol("base:this", "this", baseShell.symbol.type, source, external = true))
        val base = baseShell.copy(members = listOf(
            EtsField(EtsSymbol("base:value", "value", number, source), readonly = true),
            ctor.copy(parameters = listOf(seed), body = listOf(store(baseThis, "value", EtsReference(seed.symbol))))))
        val child = childShell.copy(members = listOf(
            EtsField(EtsSymbol("child:own", "own", number, source), readonly = true),
            ctor.copy(body = body, parameters = parameters)))
        val created = EtsSymbol("created", "created", child.symbol.type, source)
        val evaluate = EtsFunction("constructorResult", listOf(mode, seed), number, listOf(
            EtsVariable(created, EtsNew(child.symbol.type as EtsNamedType,
                listOf(EtsReference(mode.symbol), EtsReference(seed.symbol)), source), false),
            EtsReturn(EtsBinary("+", EtsMember(EtsReference(created), "value", number, source),
                EtsMember(EtsReference(created), "own", number, source), number, source), source)), source.copy(start = 4), exported = true)
        return EtsProgram(listOf(EtsFile("ConstructorFlow.kt", listOf(base, child, evaluate))))
    }
    fun normalBody(): List<EtsStatement> {
        val argument = EtsSymbol("argument", "argument", number, source)
        return listOf(choice(listOf(
            EtsVariable(argument, add(EtsReference(seed.symbol), 1), false),
            delegation.copy(arguments = listOf(EtsReference(argument))),
            store(self, "own", EtsReference(seed.symbol))), listOf(
            EtsBlock(listOf(delegation.copy(arguments = listOf(add(EtsReference(seed.symbol), 2)))), source),
            store(self, "own", add(EtsReference(seed.symbol), 3)))))
    }
}

fun checkConstructorFlowContract(): String {
    val f = ConstructorFlowFixture()
    val printer = EtsPrinter()
    val code = printer.program(f.program(f.normalBody()))
    check("super(argument);" in code && "super(seed + 2);" in code)
    fun accept(body: List<EtsStatement>) { printer.program(f.program(body)) }
    fun reject(label: String, body: List<EtsStatement>, message: String, parameters: List<EtsParameter> = f.ctor.parameters) {
        val failure = runCatching { printer.program(f.program(body, parameters)) }.exceptionOrNull()
        check(failure is InvalidTarget && message in failure.message.orEmpty() && failure.source.file == f.source.file) {
            "$label: expected source-linked $message, got $failure"
        }
    }
    val initialize = f.store(f.self, "own", f.literal(7))
    val thrown = EtsThrow(EtsLiteral("failed", EtsTypes.STRING, f.source), f.source)
    accept(listOf(EtsExpressionStatement(f.literal(1)), f.delegation, initialize))
    accept(listOf(f.choice(listOf(thrown), listOf(f.delegation)), initialize))
    accept(listOf(f.choice(listOf(f.delegation, initialize, EtsReturn(null, f.source)), listOf(f.delegation, initialize))))
    accept(listOf(f.choice(listOf(f.choice(listOf(f.delegation), listOf(f.delegation))), listOf(f.delegation)), initialize))
    accept(listOf(thrown))
    val unrelated = EtsLambda(emptyList(), listOf(EtsReturn(f.literal(1), f.source)), f.number, f.source)
    accept(listOf(EtsExpressionStatement(unrelated), f.delegation, initialize))
    reject("missing branch", listOf(f.choice(listOf(f.delegation), null)), "before super")
    reject("empty construction", emptyList(), "before super")
    reject("duplicate", listOf(f.delegation, f.delegation), "more than once")
    reject("partial duplicate", listOf(f.choice(listOf(f.delegation), null), f.delegation), "more than once")
    reject("early return", listOf(EtsReturn(null, f.source)), "before super")
    reject("early member", listOf(EtsExpressionStatement(f.own), f.delegation), "before super")
    reject("early write", listOf(initialize, f.delegation), "before super")
    reject("super argument", listOf(f.delegation.copy(arguments = listOf(f.own))), "before super")
    reject("early condition", listOf(EtsIf(listOf(EtsBranch(EtsBinary("===", f.own, f.literal(0), EtsTypes.BOOLEAN, f.source),
        listOf(f.delegation)), EtsBranch(null, listOf(f.delegation))), f.source)), "before super")
    reject("early capture", listOf(EtsExpressionStatement(unrelated.copy(body = listOf(EtsReturn(f.own, f.source)))), f.delegation), "before super")
    reject("default capture", listOf(f.delegation), "before super", listOf(f.mode, f.seed.copy(defaultValue = f.own)))
    reject("lambda super after initialization", listOf(f.delegation,
        EtsExpressionStatement(EtsLambda(emptyList(), listOf(f.delegation), EtsTypes.VOID, f.source))), "nested")
    reject("repeat allocation", listOf(EtsLoop("repeat", EtsLiteral(true, EtsTypes.BOOLEAN, f.source),
        listOf(f.delegation), false, f.source)), "loop")
    reject("return in pre-initialization loop", listOf(EtsLoop("repeat", f.condition,
        listOf(EtsReturn(null, f.source)), false, f.source), f.delegation), "before super")
    reject("wrong base", listOf(f.delegation.copy(baseClass = f.childShell.symbol.type as EtsNamedType)), "direct base")
    reject("wrong argument type", listOf(f.delegation.copy(arguments = listOf(EtsLiteral("wrong", EtsTypes.STRING, f.source)))), "type mismatch")
    val member = f.ctor.copy(name = "bad", kind = EtsFunctionKind.METHOD, body = listOf(f.delegation))
    val p = f.program(f.normalBody())
    val child = p.files.single().declarations.filterIsInstance<EtsClass>().last()
    check(runCatching { printer.program(p.copy(files = listOf(p.files.single().copy(declarations =
        p.files.single().declarations.map { if (it === child) child.copy(members = child.members + member) else it })))) }.exceptionOrNull() is InvalidTarget)
    println("PASS constructor flow: branch/block joins, abrupt exits, initialization ownership and seventeen source-linked refusals")
    return code
}

fun main(args: Array<String>) {
    val code = checkConstructorFlowContract()
    java.io.File(args.single()).writeText(code)
}
