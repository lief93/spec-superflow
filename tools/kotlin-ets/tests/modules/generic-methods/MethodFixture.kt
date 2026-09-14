package dev.ets

fun genericMethodFixture(): EtsProgram {
    fun at(file: String, offset: Int = 10) = SourceSpan("source/$file.kt", offset, offset + 5)
    fun use(parameter: EtsTypeParameter) = EtsTypeParameterType(parameter.id, parameter.name)
    fun named(declaration: EtsClass, vararg arguments: EtsType) =
        (declaration.symbol.type as EtsNamedType).copy(arguments = arguments.toList())
    fun parameter(name: String, type: EtsType, source: SourceSpan) =
        EtsParameter(EtsSymbol("parameter:${source.file}:${source.start}:$name", name, type, source))
    val reused = genericHeritageFixture().files.flatMap { it.declarations }.filterIsInstance<EtsClass>()
        .filter { it.name in setOf("TokenModel", "Readable", "Holder") }
    val model = reused.single { it.name == "TokenModel" }
    val readable = reused.single { it.name == "Readable" }
    val holder = reused.single { it.name == "Holder" }
    val read = readable.members.filterIsInstance<EtsFunction>().single()

    fun methods(file: String, context: EtsType, abstract: Boolean, names: List<String>,
        originals: List<EtsFunction> = emptyList()): List<EtsFunction> {
        fun method(name: String, offset: Int, binders: List<EtsTypeParameter>, parameters: List<EtsParameter>,
            result: EtsType, body: List<EtsStatement>) = EtsFunction(name, parameters, result,
            if (abstract) emptyList() else body, at(file, offset), kind = EtsFunctionKind.METHOD,
            typeParameters = binders, abstract = abstract,
            overrides = originals.filter { it.name == name }.map { it.symbol.id })
        val echoBinder = EtsTypeParameter("$file:echo:${names[0]}", names[0])
        val contextParameter = parameter("context", context, at(file, 20))
        val value = parameter("value", use(echoBinder), at(file, 20))
        val echo = method("echo", 20, listOf(echoBinder), listOf(contextParameter, value), use(echoBinder),
            listOf(EtsReturn(EtsReference(value.symbol), at(file, 25))))
        fun bounded(name: String, offset: Int, chain: Boolean): EtsFunction {
            val first = EtsTypeParameter("$file:$name:${names[1]}", names[1], named(readable, context))
            val second = EtsTypeParameter("$file:$name:${names[2]}", names[2], use(first))
            val reader = parameter("reader", use(if (chain) second else first), at(file, offset))
            val member = EtsMember(EtsReference(reader.symbol), "read", EtsFunctionType(emptyList(), context),
                at(file, offset + 2), read.symbol.id)
            return method(name, offset, if (chain) listOf(first, second) else listOf(first), listOf(reader), context,
                listOf(EtsReturn(EtsCall(member, emptyList(), context, at(file, offset + 3)), at(file, offset + 4))))
        }
        return listOf(echo, bounded("readBound", 40, false), bounded("readChain", 60, true))
    }
    val portBinder = EtsTypeParameter("MethodPort:C", "C")
    val portMethods = methods("MethodPort", use(portBinder), true, listOf("M", "R", "S"))
    val port = EtsClass("MethodPort", portMethods, at("MethodPort"), exported = true,
        typeParameters = listOf(portBinder), kind = EtsClassKind.INTERFACE)
    val baseBinder = EtsTypeParameter("MethodBase:C", "C")
    val baseMethods = methods("MethodBase", use(baseBinder), false, listOf("Value", "Reader", "Item"), portMethods)
    val plainValue = parameter("value", use(baseBinder), at("MethodBase", 80))
    val plain = EtsFunction("plain", listOf(plainValue), use(baseBinder),
        listOf(EtsReturn(EtsReference(plainValue.symbol), at("MethodBase", 85))), at("MethodBase", 80), kind = EtsFunctionKind.METHOD)
    val boundOnly = EtsTypeParameter("MethodBase:accept:Bound", "Bound", named(readable, named(model)))
    val accept = EtsFunction("accept", listOf(parameter("reader", use(boundOnly), at("MethodBase", 100))),
        EtsTypes.VOID, emptyList(), at("MethodBase", 100), kind = EtsFunctionKind.METHOD, typeParameters = listOf(boundOnly))
    val acceptType = EtsFunction("acceptType", emptyList(), EtsTypes.VOID, emptyList(), at("MethodBase", 120),
        kind = EtsFunctionKind.METHOD, typeParameters = listOf(EtsTypeParameter("MethodBase:acceptType:Only", "Only")))
    val constructor = EtsFunction("constructor", emptyList(), EtsTypes.VOID, emptyList(), at("MethodBase", 4),
        kind = EtsFunctionKind.CONSTRUCTOR)
    val base = EtsClass("MethodBase", listOf(constructor) + baseMethods + listOf(plain, accept, acceptType), at("MethodBase"), exported = true,
        typeParameters = listOf(baseBinder), interfaces = listOf(named(port, use(baseBinder))))
    val parent = named(base, named(model))
    val derivedMethods = methods("MethodDerived", named(model), false, listOf("Output", "View", "Element"), baseMethods)
    val derived = EtsClass("MethodDerived", listOf(EtsFunction("constructor", emptyList(), EtsTypes.VOID,
        listOf(EtsSuperConstructorCall(parent, emptyList(), at("MethodDerived", 5))), at("MethodDerived", 4),
        kind = EtsFunctionKind.CONSTRUCTOR)) + derivedMethods, at("MethodDerived"), exported = true, baseClass = parent)

    fun caller(name: String, offset: Int, receiverType: EtsType, owner: EtsClass, ownerArguments: List<EtsType>,
        declaration: EtsFunction, arguments: List<EtsType>, binders: List<EtsTypeParameter> = emptyList(),
        file: String = "MethodCalls"): EtsFunction {
        val source = at(file, offset)
        val signature = etsSubstitute(declaration.symbol.type,
            owner.typeParameters.map { it.id }.zip(ownerArguments).toMap()) as EtsFunctionType
        val instantiated = etsInstantiate(signature, arguments)
        val receiver = parameter("service", receiverType, source)
        val parameters = declaration.parameters.zip(instantiated.parameters).map { (original, type) ->
            parameter(original.symbol.name, type, source)
        }
        val member = EtsMember(EtsReference(receiver.symbol), declaration.name, signature, at(file, offset + 1), declaration.symbol.id)
        val call = EtsCall(member, parameters.map { EtsReference(it.symbol) }, instantiated.result, at(file, offset + 2), arguments)
        val body = if (instantiated.result == EtsTypes.VOID) listOf(EtsExpressionStatement(call)) else listOf(EtsReturn(call, at(file, offset + 3)))
        return EtsFunction(name, listOf(receiver) + parameters, instantiated.result, body, source,
            exported = true, typeParameters = binders)
    }
    val modelType = named(model)
    val readerType = named(holder, modelType)
    val outer = EtsTypeParameter("callBounded:Context", "Context")
    val receiverBound = EtsTypeParameter("callBounded:Service", "Service", named(port, use(outer)))
    val calls = listOf(
        caller("callDirect", 10, named(derived), derived, emptyList(), derivedMethods[0], listOf(EtsTypes.STRING)),
        caller("callBase", 30, parent, base, listOf(modelType), baseMethods[0], listOf(EtsTypes.NUMBER)),
        caller("callInterface", 50, named(port, modelType), port, listOf(modelType), portMethods[0], listOf(modelType)),
        caller("callRead", 70, named(derived), derived, emptyList(), derivedMethods[1], listOf(readerType)),
        caller("callChain", 90, named(derived), derived, emptyList(), derivedMethods[2], listOf(readerType, readerType)),
        caller("callBounded", 110, use(receiverBound), port, listOf(use(outer)), portMethods[0], listOf(EtsTypes.NUMBER),
            listOf(outer, receiverBound)),
        caller("callInherited", 130, named(derived), base, listOf(modelType), plain, emptyList()),
        caller("callAccept", 150, named(derived), base, listOf(modelType), accept, listOf(readerType)))
    val typeOnly = caller("callTypeOnly", 10, named(base, EtsTypes.NUMBER), base, listOf(EtsTypes.NUMBER),
        acceptType, listOf(modelType), file = "TypeCalls")
    return EtsProgram((reused + listOf(port, base, derived)).map { EtsFile(it.source.file!!, listOf(it)) } +
        listOf(EtsFile("source/MethodCalls.kt", calls), EtsFile("source/TypeCalls.kt", listOf(typeOnly))))
}
