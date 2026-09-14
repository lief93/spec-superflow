package dev.ets

fun checkClassIdentityContract() {
    val source = SourceSpan("Original.kt", 10, 20)
    val useSource = SourceSpan("Original.kt", 30, 40)
    val constructor = EtsFunction("constructor", emptyList(), EtsTypes.VOID, emptyList(), source,
        kind = EtsFunctionKind.CONSTRUCTOR)
    val declaration = EtsClass("Node_0", listOf(constructor), source, sourceName = "Node")
    val original = etsClassSymbol("Node", source)
    check(declaration.symbol.id == original.id)
    check(declaration.symbol.name == "Node_0" && declaration.symbol.source == source)
    check(declaration.symbol == etsClassSymbol("Node_0", source, sourceName = "Node"))
    val type = declaration.symbol.type as EtsNamedType
    val creation = EtsNew(type, emptyList(), useSource)
    val use = EtsFunction("create", emptyList(), type,
        listOf(EtsReturn(creation, useSource)), useSource)
    fun program(vararg values: EtsDeclaration) = EtsProgram(listOf(EtsFile("Emitted.kt", values.toList())))
    val printed = EtsPrinter().program(program(declaration, use))
    check("class Node_0" in printed && "new Node_0()" in printed)
    fun reject(label: String, value: EtsProgram) {
        val error = runCatching { EtsValidator().validate(value, perFileNames = true) }.exceptionOrNull()
        check(error is InvalidTarget) { "$label: expected InvalidTarget, got $error" }
        check(error.source.file == source.file)
    }
    reject("Duplicate source class identity", program(declaration, declaration.copy(name = "Other")))
    reject("Cross-file duplicate source identity", EtsProgram(listOf(
        EtsFile("One.kt", listOf(declaration)), EtsFile("Two.kt", listOf(declaration.copy(name = "Other"))))))
    fun using(value: EtsNamedType) = use.copy(body = listOf(EtsReturn(creation.copy(classType = value), useSource)))
    reject("Stale class spelling", program(declaration, using(type.copy(name = "Node"))))
    reject("Unknown source class identity", program(declaration, using(type.copy(symbolId = "unknown"))))
    check(declaration.copy(name = "Node_1").symbol.id == declaration.symbol.id)
    check(declaration.copy(source = SourceSpan("Original.kt", 50, 60)).symbol.id != declaration.symbol.id)
    println("PASS class source identity independent of emitted names and file ownership; strict binding guards")
}
