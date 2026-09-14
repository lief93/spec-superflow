package dev.ets

fun checkInheritanceContract() {
    val source = SourceSpan("Inheritance.kt", 0, 50)
    fun span(offset: Int) = source.copy(start = offset)
    val number = EtsTypes.NUMBER
    fun parameter(id: String, type: EtsType = number) = EtsParameter(EtsSymbol(id, id, type, source))
    val seed = parameter("seed")
    val signature = EtsFunction("read", listOf(parameter("extra")), number, emptyList(), span(1),
        kind = EtsFunctionKind.METHOD, abstract = true)
    val contract = EtsClass("Readable", listOf(signature), span(2), kind = EtsClassKind.INTERFACE)
    val contractType = contract.symbol.type as EtsNamedType
    val baseMethod = signature.copy(body = listOf(EtsReturn(EtsLiteral(7, number, source), source)),
        source = span(3), abstract = false, overrides = listOf(signature.symbol.id))
    val ctor = EtsFunction("constructor", listOf(seed), EtsTypes.VOID, emptyList(), span(4),
        kind = EtsFunctionKind.CONSTRUCTOR)
    val base = EtsClass("Base", listOf(ctor, baseMethod), span(5), interfaces = listOf(contractType))
    val baseType = base.symbol.type as EtsNamedType
    val delegation = EtsSuperConstructorCall(baseType, listOf(EtsReference(seed.symbol)), source)
    val child = EtsClass("Child", listOf(ctor.copy(source = span(6), body = listOf(delegation))), span(7), baseClass = baseType)
    val childType = child.symbol.type as EtsNamedType
    val receiver = parameter("receiver", childType)
    val inherited = EtsMember(EtsReference(receiver.symbol), "read", baseMethod.symbol.type, source,
        symbolId = baseMethod.symbol.id)
    val consume = EtsFunction("consume", listOf(receiver), number,
        listOf(EtsReturn(EtsCall(inherited, listOf(EtsLiteral(2, number, source)), number, source), source)), span(8))
    val upcast = EtsFunction("asReadable", listOf(receiver), contractType,
        listOf(EtsReturn(EtsReference(receiver.symbol), source)), span(9))
    val make = EtsFunction("make", emptyList(), baseType,
        listOf(EtsReturn(EtsNew(childType, listOf(EtsLiteral(1, number, source)), source), source)), span(10))
    fun program(vararg declarations: EtsDeclaration) = EtsProgram(listOf(EtsFile("Inheritance.kt", declarations.toList())))
    val declarations = arrayOf<EtsDeclaration>(contract, base, child, consume, upcast, make)
    val code = EtsPrinter().program(program(*declarations))
    check("interface Readable" in code && "read(extra: number): number;" in code)
    check("class Base implements Readable" in code && "class Child extends Base" in code)
    check("super(seed);" in code && "receiver.read(2)" in code)
    val visited = mutableListOf<EtsNode>()
    walkEts(child) { visited.add(it) }
    check(delegation.arguments.single() in visited)
    fun reject(label: String, vararg changed: EtsDeclaration) {
        val next = declarations.map { original -> changed.firstOrNull {
            when (it) { is EtsClass -> original is EtsClass && it.name == original.name
                is EtsFunction -> original is EtsFunction && it.name == original.name }
        } ?: original }
        check(runCatching { EtsPrinter().program(program(*next.toTypedArray())) }.exceptionOrNull() is InvalidTarget) { label }
    }
    reject("Missing super call", child.copy(members = listOf(ctor.copy(body = emptyList()))))
    reject("Late super call", child.copy(members = listOf(ctor.copy(body = listOf(
        EtsExpressionStatement(EtsLiteral(1, number, source)), delegation)))))
    reject("Wrong super argument", child.copy(members = listOf(ctor.copy(body = listOf(
        delegation.copy(arguments = listOf(EtsLiteral("bad", EtsTypes.STRING, source))))))))
    reject("Interface used as base class", child.copy(baseClass = contractType))
    reject("Class used as interface", base.copy(interfaces = listOf(childType)))
    reject("Heritage cycle", base.copy(baseClass = childType))
    reject("Missing interface implementation", base.copy(members = listOf(ctor)))
    reject("Wrong override identity", base.copy(members = listOf(ctor, baseMethod.copy(overrides = listOf("missing")))))
    reject("Wrong override result", base.copy(members = listOf(ctor, baseMethod.copy(returnType = EtsTypes.STRING))))
    reject("Interface body", contract.copy(members = listOf(signature.copy(body = baseMethod.body))))
    reject("Instantiate abstract class", child.copy(abstract = true))
    reject("Wrong member identity", consume.copy(body = listOf(EtsReturn(EtsCall(
        inherited.copy(symbolId = "wrong"), listOf(EtsLiteral(2, number, source)), number, source), source))))
    reject("Super outside constructor", consume.copy(body = listOf(delegation)))
    val abstractBase = base.copy(abstract = true, members = listOf(ctor, signature))
    val concreteChild = child.copy(members = child.members + baseMethod.copy(source = span(11),
        overrides = listOf(signature.symbol.id)))
    EtsPrinter().program(program(contract, abstractBase, concreteChild))
    println("PASS target inheritance contract and negative cases")
}
