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
    println("PASS named conjunctive bound contracts and eight malformed/missing-bound refusals")
}
