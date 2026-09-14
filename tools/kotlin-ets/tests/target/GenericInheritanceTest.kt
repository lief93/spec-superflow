package dev.ets

fun checkGenericInheritanceContract() {
    fun span(start: Int) = SourceSpan("GenericInheritance.kt", start, start + 1)
    val source = span(0)
    val number = EtsTypes.NUMBER
    val t = EtsTypeParameter("base:T", "T")
    val tType = EtsTypeParameterType(t.id, t.name)
    val i = EtsTypeParameter("interface:I", "I")
    val iType = EtsTypeParameterType(i.id, i.name)
    fun parameter(name: String, type: EtsType) = EtsParameter(EtsSymbol(name, name, type, source))
    val signature = EtsFunction("read", emptyList(), iType, emptyList(), span(1),
        kind = EtsFunctionKind.METHOD, abstract = true)
    val contract = EtsClass("Readable", listOf(signature), span(2), typeParameters = listOf(i),
        kind = EtsClassKind.INTERFACE)
    fun instance(declaration: EtsClass, vararg arguments: EtsType) =
        (declaration.symbol.type as EtsNamedType).copy(arguments = arguments.toList())
    val seed = parameter("seed", tType)
    val ctor = EtsFunction("constructor", listOf(seed), EtsTypes.VOID, emptyList(), span(3),
        kind = EtsFunctionKind.CONSTRUCTOR)
    val value = parameter("value", tType)
    val read = EtsFunction("read", emptyList(), tType,
        listOf(EtsReturn(EtsMember(EtsReference(EtsSymbol("this", "this",
            EtsNamedType("Base", listOf(tType), "class:GenericInheritance.kt:5:Base"), source, external = true)),
            "value", tType, source, value.symbol.id), source)), span(4),
        kind = EtsFunctionKind.METHOD, overrides = listOf(signature.symbol.id))
    val base = EtsClass("Base", listOf(ctor, EtsField(value.symbol), read), span(5),
        typeParameters = listOf(t), interfaces = listOf(instance(contract, tType)))
    val u = EtsTypeParameter("middle:U", "U")
    val uType = EtsTypeParameterType(u.id, u.name)
    val middleSeed = parameter("seed", uType)
    val middle = EtsClass("Middle", listOf(ctor.copy(parameters = listOf(middleSeed),
        body = listOf(EtsSuperConstructorCall(instance(base, uType),
            listOf(EtsReference(middleSeed.symbol)), source)), source = span(6))), span(7),
        typeParameters = listOf(u), baseClass = instance(base, uType))
    val child = EtsClass("Child", listOf(ctor.copy(parameters = emptyList(), source = span(8),
        body = listOf(EtsSuperConstructorCall(instance(middle, number),
            listOf(EtsLiteral(3, number, source)), source)))), span(9), baseClass = instance(middle, number))
    val receiver = parameter("receiver", instance(child))
    val call = EtsCall(EtsMember(EtsReference(receiver.symbol), "read",
        EtsFunctionType(emptyList(), number), source, read.symbol.id), emptyList(), number, source)
    val consume = EtsFunction("consume", listOf(receiver), number, listOf(EtsReturn(call, source)), span(10))
    val upcast = EtsFunction("asReadable", listOf(receiver), instance(contract, number),
        listOf(EtsReturn(EtsReference(receiver.symbol), source)), span(11))
    val declarations = listOf<EtsDeclaration>(contract, base, middle, child, consume, upcast)
    fun validate(values: List<EtsDeclaration>) = EtsPrinter().program(EtsProgram(listOf(EtsFile("GenericInheritance.kt", values))))
    val code = validate(declarations)
    check("class Middle<U> extends Base<U>" in code && "class Child extends Middle<number>" in code)
    check("implements Readable<T>" in code && "receiver.read()" in code)
    validate(declarations.map { if (it === child) child.copy(interfaces = listOf(instance(contract, number))) else it })
    val make = EtsFunction("make", emptyList(), instance(base, number),
        listOf(EtsReturn(EtsNew(instance(base, number), listOf(EtsLiteral(3, number, source)), source), source)), span(12))
    validate(declarations + make)
    check(runCatching { validate(declarations + make.copy(body = listOf(EtsReturn(
        EtsNew(instance(base, number), listOf(EtsLiteral("bad", EtsTypes.STRING, source)), source), source)))) }
        .exceptionOrNull() is InvalidTarget)
    val field = EtsFunction("readField", listOf(receiver), number, listOf(EtsReturn(
        EtsMember(EtsReference(receiver.symbol), "value", number, source, value.symbol.id), source)), span(13))
    validate(declarations + field)
    fun reject(label: String, original: EtsDeclaration, replacement: EtsDeclaration) {
        check(runCatching { validate(declarations.map { if (it === original) replacement else it }) }
            .exceptionOrNull() is InvalidTarget) { label }
    }
    reject("Invariant ancestor arguments", upcast, upcast.copy(returnType = instance(contract, EtsTypes.OBJECT)))
    reject("Wrong inherited member substitution", consume, consume.copy(body = listOf(EtsReturn(
        call.copy(callee = (call.callee as EtsMember).copy(type = EtsFunctionType(emptyList(), EtsTypes.STRING))), source))))
    reject("Missing ancestor arguments", child, child.copy(baseClass = instance(middle)))
    reject("Wrong super argument", child, child.copy(members = listOf((child.members.single() as EtsFunction).copy(
        body = listOf(EtsSuperConstructorCall(instance(middle, number), listOf(EtsLiteral("bad", EtsTypes.STRING, source)), source))))))
    reject("Incompatible generic diamond", child, child.copy(interfaces = listOf(instance(contract, EtsTypes.STRING))))
    reject("Wrong substituted override", base, base.copy(members = listOf(ctor, EtsField(value.symbol), read.copy(returnType = number))))
    reject("Generic heritage cycle", base, base.copy(baseClass = instance(middle, tType)))
    val bounded = base.copy(typeParameters = listOf(t.copy(upperBound = EtsTypes.OBJECT)))
    reject("Unbounded parameter violates ancestor bound", base, bounded)
    val boundedMiddle = middle.copy(typeParameters = listOf(u.copy(upperBound = EtsTypes.OBJECT)))
    validate(declarations.map { when (it) { base -> bounded; middle -> boundedMiddle; else -> it } })
    println("PASS generic target heritage, inherited substitution, bounds and negative cases")
}
