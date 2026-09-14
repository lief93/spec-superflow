package dev.ets

fun checkBoundConstraints() {
    val at = SourceSpan("BoundConstraint.kt", 1, 2)
    val read = EtsFunction("read", emptyList(), EtsTypes.NUMBER, emptyList(), at, kind = EtsFunctionKind.METHOD, abstract = true)
    val named = EtsField(EtsSymbol("name", "name", EtsTypes.STRING, at), readonly = true)
    val a = EtsClass("Readable", listOf(read), at, kind = EtsClassKind.INTERFACE)
    val b = EtsClass("Named", listOf(named), at, kind = EtsClassKind.INTERFACE)
    val parents = listOf(a.symbol.type as EtsNamedType, b.symbol.type as EtsNamedType)
    val both = EtsClass("Both", emptyList(), at, kind = EtsClassKind.INTERFACE, interfaces = parents)
    val constraint = EtsClass("Bound", emptyList(), at, kind = EtsClassKind.INTERFACE, interfaces = parents, constraint = true)
    fun program(actual: EtsType = both.symbol.type, required: EtsClass = constraint): EtsProgram {
        val input = EtsSymbol("input", "input", actual, at)
        val convert = EtsFunction("convert", listOf(EtsParameter(input)), required.symbol.type, listOf(EtsReturn(EtsReference(input), at)), at)
        return EtsProgram(listOf(EtsFile("BoundConstraint.kt", listOf(a, b, both, required, convert))))
    }
    EtsValidator().validate(program())
    fun reject(label: String, action: () -> Unit) {
        val failure = runCatching(action).exceptionOrNull()
        check(failure is InvalidTarget && failure.source == at) { "$label: $failure" }
    }
    reject("Missing second constraint") { EtsValidator().validate(program(a.symbol.type)) }
    reject("Missing first constraint") { EtsValidator().validate(program(b.symbol.type)) }
    reject("Ordinary named interfaces remain nominal") { EtsValidator().validate(program(required = constraint.copy(constraint = false))) }
    reject("Missing constraint metadata") { EtsValidator().validate(program(required = constraint.copy(interfaces = emptyList()))) }
    reject("Single bound is not an intersection") { EtsValidator().validate(program(required = constraint.copy(interfaces = parents.take(1)))) }
    reject("Duplicate bound is not an intersection") { EtsValidator().validate(program(required = constraint.copy(interfaces = listOf(parents[0], parents[0])))) }
    reject("Constraint may not invent members") { EtsValidator().validate(program(required = constraint.copy(members = listOf(read)))) }
    reject("Constraint cannot be a class") { EtsValidator().validate(program(required = constraint.copy(kind = EtsClassKind.CLASS))) }
    val base = EtsClass("Base", emptyList(), at)
    val getter = EtsFunction("name", emptyList(), EtsTypes.STRING, emptyList(), at, kind = EtsFunctionKind.GETTER, abstract = true)
    val abstractBound = EtsClass("ClassBound", listOf(getter), at, baseClass = base.symbol.type as EtsNamedType,
        interfaces = listOf(b.symbol.type as EtsNamedType), abstract = true, constraint = true)
    val implementation = EtsClass("Implementation", listOf(named.copy(initializer = EtsLiteral("name", EtsTypes.STRING, at))), at,
        baseClass = base.symbol.type as EtsNamedType, interfaces = listOf(b.symbol.type as EtsNamedType))
    fun classProgram(actual: EtsType = implementation.symbol.type, required: EtsClass = abstractBound): EtsProgram {
        val input = EtsSymbol("input", "input", actual, at)
        val convert = EtsFunction("convert", listOf(EtsParameter(input)), required.symbol.type, listOf(EtsReturn(EtsReference(input), at)), at)
        return EtsProgram(listOf(EtsFile("BoundConstraint.kt", listOf(base, b, implementation, required, convert))))
    }
    EtsValidator().validate(classProgram())
    reject("Class constraint requires the interface") { EtsValidator().validate(classProgram(base.symbol.type)) }
    reject("Class constraint requires the base") { EtsValidator().validate(classProgram(b.symbol.type)) }
    reject("Class constraint must be abstract") { EtsValidator().validate(classProgram(required = abstractBound.copy(abstract = false))) }
    reject("Class constraint cannot invent an accessor") {
        EtsValidator().validate(classProgram(required = abstractBound.copy(members = listOf(getter, getter.copy(name = "invented")))))
    }
    reject("Class constraint cannot change an inherited type") {
        EtsValidator().validate(classProgram(required = abstractBound.copy(members = listOf(getter.copy(returnType = EtsTypes.NUMBER)))))
    }
    reject("Class constraint cannot drop required accessors") { EtsValidator().validate(classProgram(required = abstractBound.copy(members = emptyList()))) }
    println("PASS named conjunctive interface/class contracts and fourteen malformed/missing-bound refusals")
}
