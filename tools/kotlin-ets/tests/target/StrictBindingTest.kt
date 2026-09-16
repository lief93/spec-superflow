package dev.ets

fun checkStrictBindingContract() {
    val source = SourceSpan("StrictBindings.kt", 0, 10)
    fun validate(vararg declarations: EtsDeclaration) = EtsPrinter().program(
        EtsProgram(listOf(EtsFile("StrictBindings.kt", declarations.toList()))))
    for (restricted in listOf("arguments", "eval")) {
        val symbol = EtsSymbol("binding:$restricted", restricted, EtsTypes.NUMBER, source)
        val parameter = EtsFunction("consume", listOf(EtsParameter(symbol)), EtsTypes.NUMBER,
            listOf(EtsReturn(EtsReference(symbol), source)), source)
        val local = parameter.copy(parameters = emptyList(), body = listOf(
            EtsVariable(symbol, EtsLiteral(1, EtsTypes.NUMBER, source), false),
            EtsReturn(EtsReference(symbol), source)))
        val constructor = parameter.copy(name = "constructor", returnType = EtsTypes.VOID,
            body = emptyList(), kind = EtsFunctionKind.CONSTRUCTOR)
        val owner = EtsClass("Owner", listOf(constructor), source)
        for (declaration in listOf<EtsDeclaration>(parameter, local, owner,
            parameter.copy(name = restricted, parameters = emptyList(), body = emptyList(), returnType = EtsTypes.VOID))) {
            val failure = runCatching { validate(declaration) }.exceptionOrNull()
            check(failure is InvalidTarget && failure.source == source) { "Strict binding $restricted was not rejected: $failure" }
        }
        val field = EtsField(symbol, EtsLiteral(1, EtsTypes.NUMBER, source))
        val legal = owner.copy(members = listOf(constructor.copy(parameters = emptyList()), field))
        check("$restricted: number" in validate(legal))
        val method = parameter.copy(name = restricted, parameters = emptyList(),
            body = listOf(EtsReturn(EtsLiteral(1, EtsTypes.NUMBER, source), source)), kind = EtsFunctionKind.METHOD)
        validate(owner.copy(members = listOf(constructor.copy(parameters = emptyList()), method)))
    }
    println("PASS strict value bindings rejected while legal field and method names are preserved")
    fun externalType(name: String, external: Boolean = true): String {
        val type = EtsNamedType(name, external = external)
        val parameter = EtsSymbol("native:parameter", "value", type, source)
        return validate(EtsFunction("identity", listOf(EtsParameter(parameter)), type,
            listOf(EtsReturn(EtsReference(parameter), source)), source))
    }
    check("resources.Configuration" in externalType("resources.Configuration"))
    for (invalid in listOf("resources..Configuration", "resources.Configuration;", ".Configuration", "resources.class")) {
        check(runCatching { externalType(invalid) }.exceptionOrNull() is InvalidTarget)
    }
    check(runCatching { externalType("Local.Class", external = false) }.exceptionOrNull() is InvalidTarget)
    println("PASS qualified native types without relaxing local declaration identifiers")
}
