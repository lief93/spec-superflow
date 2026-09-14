package dev.ets

fun checkVirtualPropertyContract() {
    fun span(start: Int) = SourceSpan("VirtualProperty.kt", start, start + 1)
    val number = EtsTypes.NUMBER
    val next = EtsParameter(EtsSymbol("next", "next", number, span(1)))
    val getter = EtsFunction("value", emptyList(), number, emptyList(), span(2),
        kind = EtsFunctionKind.GETTER, abstract = true)
    val setter = EtsFunction("value", listOf(next), EtsTypes.VOID, emptyList(), span(2),
        kind = EtsFunctionKind.SETTER, abstract = true)
    check(getter.symbol.id != setter.symbol.id)
    val base = EtsClass("Base", listOf(getter, setter), span(3), abstract = true)
    val implementationGet = getter.copy(source = span(4), abstract = false,
        body = listOf(EtsReturn(EtsLiteral(7, number, span(4)), span(4))), overrides = listOf(getter.symbol.id))
    val implementationSet = setter.copy(source = span(4), abstract = false, overrides = listOf(setter.symbol.id))
    val child = EtsClass("Child", listOf(implementationGet, implementationSet), span(5), baseClass = base.symbol.type as EtsNamedType)
    fun print(parent: EtsClass = base, derived: EtsClass = child) =
        EtsPrinter().program(EtsProgram(listOf(EtsFile("VirtualProperty.kt", listOf(parent, derived)))))
    val code = print()
    check("abstract get value(): number;" in code && "abstract set value(next: number);" in code)
    fun reject(label: String, parent: EtsClass = base, derived: EtsClass = child) {
        check(runCatching { print(parent, derived) }.exceptionOrNull() is InvalidTarget) { label }
    }
    reject("Missing setter", derived = child.copy(members = listOf(implementationGet)))
    reject("Missing getter", derived = child.copy(members = listOf(implementationSet)))
    reject("Swapped accessor identity", derived = child.copy(members = listOf(implementationGet,
        implementationSet.copy(overrides = listOf(getter.symbol.id)))))
    reject("Wrong property type", derived = child.copy(members = listOf(implementationGet.copy(returnType = EtsTypes.STRING), implementationSet)))
    reject("Abstract accessor body", parent = base.copy(members = listOf(getter.copy(body = implementationGet.body), setter)))
    reject("Abstract accessor in concrete class", parent = base.copy(abstract = false))
    val concreteBase = base.copy(abstract = false, members = listOf(
        getter.copy(abstract = false, body = implementationGet.body), setter.copy(abstract = false)))
    reject("Getter masks inherited setter", parent = concreteBase,
        derived = child.copy(members = listOf(implementationGet)))
    reject("Setter masks inherited getter", parent = concreteBase,
        derived = child.copy(members = listOf(implementationSet)))
    val contract = EtsClass("Writable", listOf(EtsField(EtsSymbol("contract-value", "value", number, span(6)))),
        span(6), kind = EtsClassKind.INTERFACE)
    val abstractImplementation = base.copy(interfaces = listOf(contract.symbol.type as EtsNamedType))
    EtsPrinter().program(EtsProgram(listOf(EtsFile("VirtualProperty.kt", listOf(contract, abstractImplementation, child)))))
    println("PASS virtual property identities, abstract accessor contracts and rejection cases")
}
