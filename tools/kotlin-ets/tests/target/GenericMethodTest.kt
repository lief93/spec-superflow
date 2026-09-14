package dev.ets

fun checkGenericMethodContract() {
    fun span(start: Int) = SourceSpan("GenericMethod.kt", start, start + 1)
    fun ref(parameter: EtsTypeParameter) = EtsTypeParameterType(parameter.id, parameter.name)
    val a = EtsTypeParameter("Contract:A", "A")
    val t = EtsTypeParameter("Contract.convert:T", "T", EtsTypes.OBJECT)
    val u = EtsTypeParameter("Impl.convert:U", "U", EtsTypes.OBJECT)
    fun method(parameter: EtsTypeParameter, argument: EtsType, start: Int, abstract: Boolean) =
        EtsFunction("convert", listOf(
            EtsParameter(EtsSymbol("$start:context", "context", argument, span(start + 1))),
            EtsParameter(EtsSymbol("$start:value", "value", ref(parameter), span(start + 2)))),
            ref(parameter), emptyList(), span(start), kind = EtsFunctionKind.METHOD,
            abstract = abstract, typeParameters = listOf(parameter))
    val required = method(t, ref(a), 10, true)
    val contract = EtsClass("Contract", listOf(required), span(1),
        kind = EtsClassKind.INTERFACE, typeParameters = listOf(a))
    val parent = (contract.symbol.type as EtsNamedType).copy(arguments = listOf(EtsTypes.NUMBER))
    val implementation = method(u, EtsTypes.NUMBER, 20, false).let {
        it.copy(body = listOf(EtsReturn(EtsReference(it.parameters[1].symbol), span(23))),
            overrides = listOf(required.symbol.id))
    }
    fun validate(value: EtsFunction = implementation, requirement: EtsFunction = required) =
        EtsPrinter().program(EtsProgram(listOf(EtsFile("GenericMethod.kt", listOf(
            contract.copy(members = listOf(requirement)),
            EtsClass("Impl", listOf(value), span(2), interfaces = listOf(parent)))))))
    val printed = validate()
    check("convert<T" in printed && "convert<U" in printed)
    fun reject(label: String, value: EtsFunction) {
        val failure = runCatching { validate(value) }.exceptionOrNull()
        check(failure is InvalidTarget) { "$label: expected InvalidTarget, got $failure" }
        check(failure.source.file == "GenericMethod.kt")
    }
    reject("Wrong override identity", implementation.copy(overrides = listOf("other:convert")))
    reject("Different return", implementation.copy(returnType = EtsTypes.NUMBER))
    reject("Different class argument", implementation.copy(parameters = implementation.parameters.mapIndexed { index, p ->
        if (index == 0) p.copy(symbol = p.symbol.copy(type = EtsTypes.STRING)) else p
    }))
    reject("Missing bound", implementation.copy(typeParameters = listOf(u.copy(upperBound = null))))
    reject("Changed bound", implementation.copy(typeParameters = listOf(u.copy(upperBound = EtsTypes.STRING))))
    reject("Extra binder", implementation.copy(typeParameters = listOf(u, EtsTypeParameter("extra:V", "V"))))
    reject("Free binder is not renamed", implementation.copy(returnType = ref(t)))
    val chainedT = EtsTypeParameter("Contract.convert:S", "S", ref(t))
    val chainedU = EtsTypeParameter("Impl.convert:V", "V", ref(u))
    validate(implementation.copy(typeParameters = listOf(u, chainedU)),
        required.copy(typeParameters = listOf(t, chainedT)))
    println("PASS generic method binder correspondence, class substitution and strict override signatures")
}
