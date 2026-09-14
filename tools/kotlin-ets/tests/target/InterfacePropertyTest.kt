package dev.ets

fun checkInterfacePropertyContract() {
    val at = SourceSpan("Property.kt", 0, 20)
    val number = EtsTypes.NUMBER
    val requirement = EtsField(EtsSymbol("property", "value", number, at))
    val contract = EtsClass("Property", listOf(requirement), at, kind = EtsClassKind.INTERFACE)
    val contractType = contract.symbol.type as EtsNamedType
    val storage = EtsField(EtsSymbol("storage", "value", number, at), EtsLiteral(1, number, at))
    val ctor = EtsFunction("constructor", emptyList(), EtsTypes.VOID, emptyList(), at, kind = EtsFunctionKind.CONSTRUCTOR)
    val implementation = EtsClass("Stored", listOf(storage, ctor), at, interfaces = listOf(contractType))
    val getter = EtsFunction("value", emptyList(), number, listOf(EtsReturn(EtsLiteral(1, number, at), at)),
        at, kind = EtsFunctionKind.GETTER)
    val next = EtsParameter(EtsSymbol("next", "next", number, at))
    val setter = EtsFunction("value", listOf(next), EtsTypes.VOID, emptyList(), at, kind = EtsFunctionKind.SETTER)
    fun print(api: EtsClass = contract, impl: EtsClass = implementation, extra: List<EtsDeclaration> = emptyList()): String =
        EtsPrinter().program(EtsProgram(listOf(EtsFile("Property.kt", listOf(api, impl) + extra))))
    fun reject(label: String, api: EtsClass = contract, impl: EtsClass = implementation, extra: List<EtsDeclaration> = emptyList()) {
        check(runCatching { print(api, impl, extra) }.exceptionOrNull() is InvalidTarget) { label }
    }
    check("value: number;" in print())
    val readonly = contract.copy(members = listOf(requirement.copy(readonly = true)))
    check("readonly value: number;" in print(readonly))
    print(impl = implementation.copy(members = listOf(getter, setter, ctor)))
    print(readonly, implementation.copy(members = listOf(getter, ctor)))
    reject("Missing storage", impl = implementation.copy(members = listOf(ctor)))
    reject("Wrong type", impl = implementation.copy(members = listOf(storage.copy(
        symbol = storage.symbol.copy(type = EtsTypes.STRING), initializer = EtsLiteral("x", EtsTypes.STRING, at)), ctor)))
    reject("Readonly implementation of var", impl = implementation.copy(members = listOf(storage.copy(readonly = true), ctor)))
    reject("Missing setter", impl = implementation.copy(members = listOf(getter, ctor)))
    reject("Wrong setter type", impl = implementation.copy(members = listOf(getter,
        setter.copy(parameters = listOf(next.copy(symbol = next.symbol.copy(type = EtsTypes.STRING)))), ctor)))
    reject("Private implementation", impl = implementation.copy(members = listOf(storage.copy(visibility = EtsVisibility.PRIVATE), ctor)))
    reject("Initialized interface", api = contract.copy(members = listOf(requirement.copy(initializer = EtsLiteral(0, number, at)))))
    val receiver = EtsParameter(EtsSymbol("receiver", "receiver", contractType, at))
    val write = EtsFunction("write", listOf(receiver), EtsTypes.VOID, listOf(EtsExpressionStatement(EtsAssignment(
        EtsMember(EtsReference(receiver.symbol), "value", number, at), EtsLiteral(2, number, at), at), at)), at)
    print(extra = listOf(write))
    reject("Write through readonly interface", api = readonly, extra = listOf(write))
    println("PASS interface property signatures, implementations and eight rejection cases")
}
