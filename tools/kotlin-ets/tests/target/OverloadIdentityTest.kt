package dev.ets

fun checkOverloadIdentityContract() {
    fun span(start: Int) = SourceSpan("Overloads.kt", start, start + 1)
    fun method(name: String, start: Int) = EtsFunction(name, emptyList(), EtsTypes.NUMBER,
        listOf(EtsReturn(EtsLiteral(start, EtsTypes.NUMBER, span(start)), span(start))), span(start),
        sourceName = "select")
    val first = method("select", 10)
    val second = method("select_0", 20)
    check(second.symbol.id == etsFunctionSymbol("select", emptyList(), EtsTypes.NUMBER, span(20)).id)
    check(second.symbol.name == "select_0" && second.symbol.source == span(20))
    check(second.symbol == etsFunctionSymbol("select_0", emptyList(), EtsTypes.NUMBER, span(20), sourceName = "select"))
    val call = EtsCall(EtsReference(second.symbol), emptyList(), EtsTypes.NUMBER, span(40))
    val use = EtsFunction("use", emptyList(), EtsTypes.NUMBER,
        listOf(EtsReturn(call, span(40))), span(30))
    fun program(vararg declarations: EtsDeclaration) = EtsProgram(listOf(EtsFile("Overloads.kt", declarations.toList())))
    val printed = EtsPrinter().program(program(first, second, use))
    check("function select_0(" in printed && "return select_0();" in printed)
    fun reject(label: String, value: EtsProgram) {
        val error = runCatching { EtsValidator().validate(value, perFileNames = true) }.exceptionOrNull()
        check(error is InvalidTarget) { "$label: expected InvalidTarget, got $error" }
        check(error.source.file == "Overloads.kt")
    }
    reject("Duplicate canonical function identity", program(first, first.copy(name = "different")))
    reject("Cross-file duplicate identity", EtsProgram(listOf(EtsFile("One.kt", listOf(first)),
        EtsFile("Two.kt", listOf(first.copy(name = "different"))))))
    fun using(symbol: EtsSymbol) = use.copy(body = listOf(EtsReturn(call.copy(callee = EtsReference(symbol)), span(40))))
    reject("Canonical identity with stale spelling", program(first, second, using(second.symbol.copy(name = "select"))))
    reject("Spelling with wrong identity", program(first, second, using(second.symbol.copy(id = first.symbol.id))))
    reject("Canonical identity with stale type", program(first, second, using(second.symbol.copy(type = EtsFunctionType(emptyList(), EtsTypes.STRING)))))
    val owner = EtsClass("Selector", listOf(first.copy(kind = EtsFunctionKind.METHOD),
        second.copy(kind = EtsFunctionKind.METHOD)), span(50))
    EtsValidator().validate(program(owner))
    reject("Duplicate member identity", program(owner.copy(members = listOf(
        first.copy(kind = EtsFunctionKind.METHOD), first.copy(name = "different", kind = EtsFunctionKind.METHOD)))))
    println("PASS overload source identity, emitted spelling and strict declaration/reference binding")
}
