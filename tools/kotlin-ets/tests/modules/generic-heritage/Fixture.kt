package dev.ets

fun genericHeritageFixture(): EtsProgram {
    fun at(file: String, offset: Int = 10) = SourceSpan("source/$file.kt", offset, offset + 5)
    fun parameter(id: String, name: String, type: EtsType, source: SourceSpan) =
        EtsParameter(EtsSymbol(id, name, type, source))
    fun named(declaration: EtsClass, vararg arguments: EtsType) =
        (declaration.symbol.type as EtsNamedType).copy(arguments = arguments.toList())
    fun binder(id: String) = EtsTypeParameter(id, "T")
    fun use(binder: EtsTypeParameter) = EtsTypeParameterType(binder.id, binder.name)
    fun receiver(declaration: EtsClass, type: EtsNamedType) = EtsReference(EtsSymbol(
        "receiver:${declaration.symbol.id}", "this", type, declaration.source, external = true))

    val modelShell = EtsClass("TokenModel", emptyList(), at("TokenModel"), exported = true)
    val text = EtsSymbol("field:TokenModel:text", "text", EtsTypes.STRING, at("TokenModel", 20))
    val textParameter = parameter("parameter:TokenModel:text", "text", EtsTypes.STRING, at("TokenModel", 30))
    val textTarget = EtsMember(receiver(modelShell, named(modelShell)), text.name, text.type, text.source, text.id)
    val model = modelShell.copy(members = listOf(EtsField(text), EtsFunction("constructor", listOf(textParameter),
        EtsTypes.VOID, listOf(EtsExpressionStatement(EtsAssignment(textTarget, EtsReference(textParameter.symbol),
            textParameter.symbol.source))), textParameter.symbol.source, kind = EtsFunctionKind.CONSTRUCTOR)))

    val readableBinder = binder("binder:Readable:T")
    val readableRead = EtsFunction("read", emptyList(), use(readableBinder), emptyList(), at("Readable", 20),
        kind = EtsFunctionKind.METHOD, abstract = true)
    val readable = EtsClass("Readable", listOf(readableRead), at("Readable"), exported = true,
        typeParameters = listOf(readableBinder), kind = EtsClassKind.INTERFACE)

    val holderBinder = binder("binder:Holder:T")
    val holderShell = EtsClass("Holder", emptyList(), at("Holder"), exported = true,
        typeParameters = listOf(holderBinder), interfaces = listOf(named(readable, use(holderBinder))))
    val stored = EtsSymbol("field:Holder:stored", "stored", use(holderBinder), at("Holder", 20))
    val initial = parameter("parameter:Holder:value", "value", use(holderBinder), at("Holder", 30))
    fun storedReference(source: SourceSpan) = EtsMember(receiver(holderShell, named(holderShell, use(holderBinder))),
        stored.name, stored.type, source, stored.id)
    val read = EtsFunction("read", emptyList(), use(holderBinder), listOf(EtsReturn(storedReference(at("Holder", 40)),
        at("Holder", 40))), at("Holder", 40), kind = EtsFunctionKind.METHOD, overrides = listOf(readableRead.symbol.id))
    val holder = holderShell.copy(members = listOf(EtsField(stored), EtsFunction("constructor", listOf(initial),
        EtsTypes.VOID, listOf(EtsExpressionStatement(EtsAssignment(storedReference(initial.symbol.source),
            EtsReference(initial.symbol), initial.symbol.source))), initial.symbol.source, kind = EtsFunctionKind.CONSTRUCTOR), read))

    val middleBinder = binder("binder:Middle:T")
    val middleParent = named(holder, use(middleBinder))
    val middleValue = parameter("parameter:Middle:value", "value", use(middleBinder), at("Middle", 20))
    val middle = EtsClass("Middle", listOf(EtsFunction("constructor", listOf(middleValue), EtsTypes.VOID,
        listOf(EtsSuperConstructorCall(middleParent, listOf(EtsReference(middleValue.symbol)), middleValue.symbol.source)),
        middleValue.symbol.source, kind = EtsFunctionKind.CONSTRUCTOR)), at("Middle"), exported = true,
        typeParameters = listOf(middleBinder), baseClass = middleParent)

    fun concrete(name: String, argument: EtsType): EtsClass {
        val parent = named(middle, argument)
        val value = parameter("parameter:$name:value", "value", argument, at(name, 20))
        return EtsClass(name, listOf(EtsFunction("constructor", listOf(value), EtsTypes.VOID,
            listOf(EtsSuperConstructorCall(parent, listOf(EtsReference(value.symbol)), value.symbol.source)),
            value.symbol.source, kind = EtsFunctionKind.CONSTRUCTOR)), at(name), exported = true, baseClass = parent)
    }
    val textHolder = concrete("TextHolder", EtsTypes.STRING)
    val modelHolder = concrete("ModelHolder", named(model))

    fun consumer(name: String, parameterName: String, type: EtsNamedType, result: EtsType, member: EtsFunction,
        offset: Int, typeParameters: List<EtsTypeParameter> = emptyList()): EtsFunction {
        val source = at("Consumers", offset)
        val value = parameter("parameter:$name:$parameterName", parameterName, type, source)
        val callee = EtsMember(EtsReference(value.symbol), member.name, EtsFunctionType(emptyList(), result), source,
            symbolId = member.symbol.id)
        return EtsFunction(name, listOf(value), result, listOf(EtsReturn(EtsCall(callee, emptyList(), result, source), source)),
            source, exported = true, typeParameters = typeParameters)
    }
    val genericBinder = binder("binder:readGeneric:T")
    val consumers = listOf(
        consumer("readDirect", "model", named(modelHolder), named(model), read, 10),
        consumer("readBase", "base", named(holder, named(model)), named(model), read, 20),
        consumer("readInterface", "view", named(readable, named(model)), named(model), readableRead, 30),
        consumer("readGeneric", "value", named(middle, use(genericBinder)), use(genericBinder), read, 40,
            listOf(genericBinder)),
        consumer("readText", "value", named(textHolder), EtsTypes.STRING, read, 50))
    val classes = listOf(readable, model, holder, middle, textHolder, modelHolder)
    return EtsProgram(classes.map { EtsFile(it.source.file!!, listOf(it)) } + EtsFile("source/Consumers.kt", consumers))
}
