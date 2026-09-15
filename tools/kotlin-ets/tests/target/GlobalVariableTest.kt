package dev.ets

fun checkGlobalVariableContract() {
    val source = SourceSpan("State.kt", 0, 20)
    val other = SourceSpan("Page.kt", 0, 20)
    val symbol = EtsSymbol("global:page", "page", EtsTypes.NUMBER, source)
    val global = EtsGlobal(symbol, EtsLiteral(0, EtsTypes.NUMBER, source), mutable = true, exported = true)
    val write = EtsExpressionStatement(EtsAssignment(EtsReference(symbol), EtsLiteral(2, EtsTypes.NUMBER, source), source))
    val setter = EtsFunction("setPage", emptyList(), EtsTypes.VOID, listOf(write), source, exported = true)
    val reader = EtsFunction("readPage", emptyList(), EtsTypes.NUMBER,
        listOf(EtsReturn(EtsReference(symbol, other), other)), other, exported = true)
    val program = EtsProgram(listOf(EtsFile("State.kt", listOf(global, setter)), EtsFile("Page.kt", listOf(reader))))
    EtsValidator().validate(program)
    check("export let page: number = 0;" in EtsPrinter().program(program))
    val visited = mutableListOf<EtsNode>()
    walkEts(global, visited::add)
    check(visited == listOf(global, global.initializer))
    fun rejected(value: EtsProgram, reason: String) {
        val error = runCatching { EtsValidator().validate(value) }.exceptionOrNull()
        check(error is InvalidTarget && reason in error.message.orEmpty()) { "$reason: $error" }
    }
    rejected(program.copy(files = listOf(EtsFile("State.kt", listOf(global.copy(mutable = false), setter)))), "readonly target global")
    rejected(program.copy(files = listOf(EtsFile("State.kt", listOf(global)),
        EtsFile("Page.kt", listOf(setter.copy(source = other))))), "owner-file setter")
    rejected(program.copy(files = listOf(EtsFile("State.kt", listOf(global.copy(
        initializer = EtsLiteral("wrong", EtsTypes.STRING, source)))))), "type")
    rejected(program.copy(files = listOf(EtsFile("State.kt", listOf(global, global)))), "Duplicate target declaration identity")
    rejected(program.copy(files = listOf(EtsFile("State.kt", listOf(global,
        reader.copy(name = "page", source = source))))), "Conflicting target declaration")
    println("Global variable target contract: reads, own-file writes, printing/traversal and five rejections passed")
}
