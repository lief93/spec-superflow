package dev.ets

fun checkBoundedReceiverContract() {
    fun span(start: Int) = SourceSpan("BoundedReceiver.kt", start, start + 1)
    val source = span(0)
    val resultParameter = EtsTypeParameter("Readable:R", "R")
    val resultType = EtsTypeParameterType(resultParameter.id, resultParameter.name)
    val read = EtsFunction("read", emptyList(), resultType, emptyList(), span(1),
        kind = EtsFunctionKind.METHOD, abstract = true)
    val readable = EtsClass("Readable", listOf(read), span(2),
        typeParameters = listOf(resultParameter), kind = EtsClassKind.INTERFACE)
    fun named(declaration: EtsClass, vararg arguments: EtsType) =
        (declaration.symbol.type as EtsNamedType).copy(arguments = arguments.toList())
    val bound = named(readable, EtsTypes.NUMBER)
    val t = EtsTypeParameter("consume:T", "T", upperBound = bound)
    val tType = EtsTypeParameterType(t.id, t.name)
    val receiver = EtsSymbol("consume:receiver", "receiver", tType, span(3))
    val member = EtsMember(EtsReference(receiver), "read",
        EtsFunctionType(emptyList(), EtsTypes.NUMBER), span(4), read.symbol.id)
    fun consume(parameters: List<EtsTypeParameter> = listOf(t), value: EtsMember = member) =
        EtsFunction("consume", listOf(EtsParameter(receiver)), EtsTypes.NUMBER,
            listOf(EtsReturn(EtsCall(value, emptyList(), EtsTypes.NUMBER, span(5)), span(6))),
            span(7), typeParameters = parameters)
    fun validate(function: EtsFunction, declarations: List<EtsDeclaration> = listOf(readable)) =
        EtsPrinter().program(EtsProgram(listOf(EtsFile("BoundedReceiver.kt", declarations + function))))
    check("receiver.read()" in validate(consume()))
    val extraArguments = consume().copy(body = listOf(EtsReturn(
        EtsCall(member, emptyList(), EtsTypes.NUMBER, span(5), typeArguments = listOf(EtsTypes.NUMBER)), span(6))))
    check(runCatching { validate(extraArguments) }.exceptionOrNull() is InvalidTarget) {
        "Non-generic bounded method must reject target type arguments"
    }
    fun reject(label: String, function: EtsFunction) {
        val failure = runCatching { validate(function) }.exceptionOrNull()
        check(failure is InvalidTarget) { "$label: expected InvalidTarget, got $failure" }
        check(failure.source.file == source.file)
    }
    reject("Wrong member identity", consume(value = member.copy(symbolId = "unrelated:read")))
    reject("Missing member identity", consume(value = member.copy(symbolId = null)))
    reject("Missing member", consume(value = member.copy(name = "missing")))
    reject("Wrong member signature", consume(value = member.copy(type = EtsFunctionType(emptyList(), EtsTypes.STRING))))
    reject("Unbounded receiver", consume(listOf(t.copy(upperBound = null))))
    reject("Nullable bound", consume(listOf(t.copy(upperBound = EtsNullableType(bound)))))
    reject("Opaque bound", consume(listOf(t.copy(upperBound = EtsNamedType("External", external = true)))))
    reject("Primitive bound", consume(listOf(t.copy(upperBound = EtsTypes.NUMBER))))
    val u = EtsTypeParameter("consume:U", "U", upperBound = bound)
    val uType = EtsTypeParameterType(u.id, u.name)
    validate(consume(listOf(u, t.copy(upperBound = uType))))
    reject("Bound chain cycle", consume(listOf(u.copy(upperBound = tType), t.copy(upperBound = uType))))
    val parentParameter = EtsTypeParameter("Parent:P", "P")
    val parentType = EtsTypeParameterType(parentParameter.id, parentParameter.name)
    val parentRead = read.copy(returnType = parentType, source = span(14), overrides = listOf(read.symbol.id))
    val parent = EtsClass("Parent", listOf(parentRead), span(8), abstract = true,
        typeParameters = listOf(parentParameter), interfaces = listOf(named(readable, parentType)))
    validate(consume(listOf(t.copy(upperBound = named(parent, EtsTypes.NUMBER))), member.copy(symbolId = parentRead.symbol.id)), listOf(readable, parent))
    val middle = EtsClass("Middle", emptyList(), span(15), abstract = true,
        baseClass = named(parent, EtsTypes.NUMBER))
    validate(consume(listOf(t.copy(upperBound = named(middle))), member.copy(symbolId = parentRead.symbol.id)), listOf(readable, parent, middle))
    val selfParameter = EtsTypeParameter("Self:S", "S")
    val selfType = EtsTypeParameterType(selfParameter.id, selfParameter.name)
    val self = EtsFunction("self", emptyList(), selfType, emptyList(), span(9),
        kind = EtsFunctionKind.METHOD, abstract = true)
    val selfContract = EtsClass("Self", listOf(self), span(10),
        typeParameters = listOf(selfParameter), kind = EtsClassKind.INTERFACE)
    val selfMember = EtsMember(EtsReference(receiver), "self",
        EtsFunctionType(emptyList(), tType), span(11), self.symbol.id)
    val recursive = consume(listOf(t.copy(upperBound = named(selfContract, tType))))
        .copy(returnType = tType, body = listOf(EtsReturn(
            EtsCall(selfMember, emptyList(), tType, span(12)), span(13))))
    validate(recursive, listOf(selfContract))
    println("PASS bounded receiver identity, signatures, chains, inherited arguments and named F-bounds")
}
