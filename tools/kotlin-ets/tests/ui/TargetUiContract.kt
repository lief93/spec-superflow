package dev.ets

fun main() {
    val source = SourceSpan("Ui.kt", 10, 20)
    fun call(name: String, parameter: EtsType, value: EtsExpression) = EtsCall(
        EtsReference(EtsSymbol("arkui:$name", name, EtsFunctionType(listOf(parameter), EtsTypes.VOID), source, true)),
        listOf(value), EtsTypes.VOID, source)
    val text = EtsUiElement(call("Text", EtsTypes.STRING, EtsLiteral("hello", EtsTypes.STRING, source)), source = source)
    fun program(body: List<EtsStatement>, builder: Boolean = true) = EtsProgram(listOf(EtsFile("Ui.kt", listOf(
        EtsClass("Page", listOf(EtsFunction("content", emptyList(), EtsTypes.VOID, body, source,
            kind = EtsFunctionKind.METHOD, builder = builder)), source, component = true)))))
    var selected = false
    val runtime = EtsRuntimeSupport { selected = true; emptyList() }
    val output = emitEtsProgram(program(listOf(text)), runtime)
    check(selected && "@Component" in output && "@Builder" in output && "Text(\"hello\")" in output)
    val visited = mutableListOf<EtsNode>()
    program(listOf(text)).files.single().declarations.forEach { walkEts(it, visited::add) }
    check(visited.any { it is EtsLiteral && it.value == "hello" })
    fun rejected(value: EtsProgram) {
        selected = false
        val failure = runCatching { emitEtsProgram(value, runtime) }.exceptionOrNull()
        check(failure is InvalidTarget && failure.source == source && !selected)
    }
    rejected(program(listOf(text.copy(call = call("Text", EtsTypes.STRING, EtsLiteral(1, EtsTypes.NUMBER, source))))))
    rejected(program(listOf(text), builder = false))
    val padding = EtsRecordType("Padding", linkedMapOf("left" to EtsTypes.NUMBER))
    val bad = EtsObject(linkedMapOf("left" to EtsLiteral("wrong", EtsTypes.STRING, source)), padding, source)
    rejected(program(listOf(text.copy(attributes = listOf(call("padding", padding, bad))))))
    val branch = EtsIf(listOf(EtsBranch(EtsLiteral(true, EtsTypes.BOOLEAN, source), listOf(text)),
        EtsBranch(null, listOf(text))), source)
    check("if (true)" in emitEtsProgram(program(listOf(branch)), runtime))
    rejected(program(listOf(branch.copy(branches = listOf(EtsBranch(EtsLiteral(1, EtsTypes.NUMBER, source), listOf(text)))))))
    val item = EtsParameter(EtsSymbol("item", "item", EtsTypes.STRING, source))
    val loop = EtsUiForEach(EtsArray(listOf(EtsLiteral("a", EtsTypes.STRING, source)), EtsTypes.STRING, source), item,
        listOf(EtsUiElement(call("Text", EtsTypes.STRING, EtsReference(item.symbol)))), source)
    check("ForEach(" in emitEtsProgram(program(listOf(loop)), runtime))
    rejected(program(listOf(loop.copy(item = EtsParameter(item.symbol.copy(type = EtsTypes.NUMBER))))))
    val callback = EtsLambda(emptyList(), listOf(text), EtsTypes.VOID, source)
    rejected(program(listOf(text.copy(attributes = listOf(call("onClick", callback.type, callback))))))
    println("PASS typed UI output, exhaustive traversal, bad property type and ordinary-function UI rejection before runtime")
}
