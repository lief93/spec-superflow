package dev.ets

fun checkVisibilityContract() {
    val at = SourceSpan("Visibility.kt", 12, 40)
    val constructor = EtsFunction("constructor", emptyList(), EtsTypes.VOID, emptyList(), at,
        kind = EtsFunctionKind.CONSTRUCTOR, visibility = EtsVisibility.PRIVATE)
    val owner = EtsClass("Hidden", listOf(constructor), at)
    val create = EtsFunction("create", emptyList(), owner.symbol.type,
        listOf(EtsReturn(EtsNew(owner.symbol.type as EtsNamedType, emptyList(), at), at)), at.copy(start = 41))
    val failure = runCatching {
        EtsPrinter().program(EtsProgram(listOf(EtsFile("Visibility.kt", listOf(owner, create)))))
    }.exceptionOrNull()
    check(failure is InvalidTarget && "constructor access" in failure.message.orEmpty() && failure.source == at) {
        "External allocation must reject private constructor with source evidence: $failure"
    }
    val base = owner.copy(name = "Base", members = emptyList())
    val baseType = base.symbol.type as EtsNamedType
    val child = EtsClass("Child", emptyList(), at.copy(start = 50), baseClass = baseType)
    val childType = child.symbol.type as EtsNamedType
    val peer = EtsClass("Peer", emptyList(), at.copy(start = 51), baseClass = baseType)
    val peerType = peer.symbol.type as EtsNamedType
    val delegate = EtsSuperConstructorCall(baseType, emptyList(), at)
    val childConstructor = constructor.copy(body = listOf(delegate), visibility = EtsVisibility.PUBLIC)
    val field = EtsField(EtsSymbol("base:secret", "secret", EtsTypes.NUMBER, at),
        EtsLiteral(3, EtsTypes.NUMBER, at), visibility = EtsVisibility.PROTECTED)
    val protectedConstructor = constructor.copy(visibility = EtsVisibility.PROTECTED)
    val reader = EtsFunction("read", emptyList(), EtsTypes.NUMBER,
        listOf(EtsReturn(EtsLiteral(3, EtsTypes.NUMBER, at), at)), at.copy(start = 15),
        kind = EtsFunctionKind.METHOD, visibility = EtsVisibility.PROTECTED)
    val getter = reader.copy(name = "value", kind = EtsFunctionKind.GETTER, visibility = EtsVisibility.PUBLIC)
    val parameter = EtsParameter(EtsSymbol("write:value", "value", EtsTypes.NUMBER, at))
    val setter = reader.copy(name = "value", kind = EtsFunctionKind.SETTER, returnType = EtsTypes.VOID,
        parameters = listOf(parameter), body = emptyList(), visibility = EtsVisibility.PRIVATE)
    fun access(receiver: EtsNamedType, member: String = "secret", write: Boolean = false): EtsFunction {
        val argument = EtsParameter(EtsSymbol("access:other", "other", receiver, at))
        val value = EtsMember(EtsReference(argument.symbol), member, EtsTypes.NUMBER, at)
        return EtsFunction("access", listOf(argument), EtsTypes.VOID,
            listOf(EtsExpressionStatement(if (write) EtsAssignment(value, EtsLiteral(1, EtsTypes.NUMBER, at), at) else value)),
            at.copy(start = 60), kind = EtsFunctionKind.METHOD)
    }
    fun program(extra: List<EtsClassMember> = emptyList(), baseMembers: List<EtsClassMember> =
        listOf(protectedConstructor, field, reader, getter, setter), globals: List<EtsDeclaration> = emptyList()): EtsProgram =
        EtsProgram(listOf(EtsFile("Visibility.kt", listOf(base.copy(members = baseMembers),
            child.copy(members = listOf(childConstructor) + extra), peer.copy(members = listOf(childConstructor))) + globals)))
    var refused = 1
    fun reject(label: String, input: EtsProgram, message: String) {
        val error = runCatching { EtsPrinter().program(input) }.exceptionOrNull()
        check(error is InvalidTarget && message in error.message.orEmpty() && error.source.file == at.file) { "$label: $error" }
        refused++
    }
    val printer = EtsPrinter()
    val code = printer.program(program(listOf(access(childType))))
    check("protected constructor()" in code && "protected secret: number" in code && "protected read()" in code)
    check("private set value(" in code)
    printer.program(program(listOf(access(childType, "value"))))
    reject("base receiver in derived scope", program(listOf(access(baseType))), "member access")
    reject("sibling receiver", program(listOf(access(peerType))), "member access")
    reject("private inherited field", program(listOf(access(childType)),
        listOf(protectedConstructor, field.copy(visibility = EtsVisibility.PRIVATE))), "member access")
    reject("private setter in subclass", program(listOf(access(childType, "value", write = true))), "member access")
    reject("private base constructor", program(baseMembers = listOf(constructor)), "constructor access")
    reject("protected external allocation", program(globals = listOf(create.copy(returnType = baseType,
        body = listOf(EtsReturn(EtsNew(baseType, emptyList(), at), at))))), "constructor access")
    val allocateBase = create.copy(kind = EtsFunctionKind.METHOD, returnType = baseType,
        body = listOf(EtsReturn(EtsNew(baseType, emptyList(), at), at)))
    reject("protected allocation from subclass", program(listOf(allocateBase)), "constructor access")
    printer.program(program(baseMembers = listOf(protectedConstructor, allocateBase)))
    reject("protected global function", program(globals = listOf(create.copy(visibility = EtsVisibility.PROTECTED))), "class ownership")
    val override = reader.copy(visibility = EtsVisibility.PUBLIC, source = at.copy(start = 70), overrides = listOf(reader.symbol.id))
    printer.program(program(listOf(override)))
    reject("narrowed override", program(listOf(override.copy(visibility = EtsVisibility.PROTECTED)),
        listOf(protectedConstructor, reader.copy(visibility = EtsVisibility.PUBLIC))), "override signature")
    reject("implicit narrowed override", program(listOf(override.copy(visibility = EtsVisibility.PROTECTED, overrides = emptyList())),
        listOf(protectedConstructor, reader.copy(visibility = EtsVisibility.PUBLIC))), "inherited target method")
    val static = reader.copy(name = "factory", static = true)
    val useStatic = access(childType).copy(parameters = emptyList(), body = listOf(EtsExpressionStatement(
        EtsCall(EtsMember(EtsReference(base.symbol), "factory", static.symbol.type, at, static.symbol.id), emptyList(), EtsTypes.NUMBER, at))))
    printer.program(program(listOf(useStatic), listOf(protectedConstructor, static)))
    reject("external protected static method", program(baseMembers = listOf(protectedConstructor, static),
        globals = listOf(useStatic.copy(kind = EtsFunctionKind.FUNCTION))), "member access")
    val runtimeType = EtsNamedType("RuntimeBase", symbolId = "runtime:RuntimeBase", external = true)
    val runtime = base.copy(name = "RuntimeBase", members = listOf(protectedConstructor.copy(
        parameters = listOf(parameter), visibility = EtsVisibility.PUBLIC)))
    fun externalProgram(argument: EtsExpression) = EtsProgram(listOf(EtsFile("Visibility.kt", listOf(
        child.copy(baseClass = runtimeType, members = listOf(childConstructor.copy(body = listOf(
            EtsSuperConstructorCall(runtimeType, listOf(argument), at)))))))),
        externalClasses = mapOf("runtime:RuntimeBase" to runtime))
    printer.program(externalProgram(EtsLiteral(1, EtsTypes.NUMBER, at)))
    reject("external constructor contract", externalProgram(EtsLiteral("wrong", EtsTypes.STRING, at)), "type mismatch")
    reject("undeclared external heritage", externalProgram(EtsLiteral(1, EtsTypes.NUMBER, at)).copy(externalClasses = emptyMap()),
        "Unbound target heritage")
    println("PASS typed member visibility: protected super, fields, methods, accessors and $refused source-linked refusals")
}
