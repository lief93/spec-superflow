package dev.ets

fun overloadModuleFixture(): EtsProgram {
    fun at(file: String, offset: Int = 10) = SourceSpan("source/$file.kt", offset, offset + 5)
    fun parameter(name: String, type: EtsType, source: SourceSpan) =
        EtsParameter(EtsSymbol("parameter:${source.file}:${source.start}:$name", name, type, source))
    val model = genericHeritageFixture().files.flatMap { it.declarations }.filterIsInstance<EtsClass>()
        .single { it.name == "TokenModel" }
    fun identity(file: String, offset: Int, emitted: String, type: EtsType, sourceName: String? = null,
        member: Boolean = false, static: Boolean = false, increment: Boolean = false): EtsFunction {
        val source = at(file, offset)
        val value = parameter("value", type, source)
        val reference = EtsReference(value.symbol)
        val result = if (increment) EtsBinary("+", reference, EtsLiteral(1, EtsTypes.NUMBER, source), type, source) else reference
        return EtsFunction(emitted, listOf(value), type, listOf(EtsReturn(result, source)), source,
            kind = if (member) EtsFunctionKind.METHOD else EtsFunctionKind.FUNCTION,
            exported = !member, static = static, sourceName = sourceName)
    }
    fun pair(file: String, offset: Int, emitted: String, sourceName: String, member: Boolean = false): EtsFunction {
        val source = at(file, offset)
        val left = parameter("left", EtsTypes.NUMBER, source)
        val right = parameter("right", EtsTypes.NUMBER, source)
        return EtsFunction(emitted, listOf(left, right), EtsTypes.NUMBER, listOf(EtsReturn(EtsBinary("+",
            EtsReference(left.symbol), EtsReference(right.symbol), EtsTypes.NUMBER, source), source)), source,
            kind = if (member) EtsFunctionKind.METHOD else EtsFunctionKind.FUNCTION,
            exported = !member, sourceName = sourceName)
    }
    fun reserved(file: String, offset: Int, name: String, member: Boolean = false) = EtsFunction(name,
        emptyList(), EtsTypes.STRING, listOf(EtsReturn(EtsLiteral("reserved", EtsTypes.STRING, at(file, offset)), at(file, offset))),
        at(file, offset), kind = if (member) EtsFunctionKind.METHOD else EtsFunctionKind.FUNCTION, exported = !member)
    // These spellings are preallocated target input, not an output naming algorithm.
    val number = identity("Numbers", 10, "select", EtsTypes.NUMBER)
    val secondNumber = identity("Numbers", 20, "select_1", EtsTypes.NUMBER, "select", increment = true)
    val twoNumbers = pair("Numbers", 30, "select_2", "select")
    val unique = reserved("Numbers", 40, "select_0")
    val text = identity("Texts", 10, "render", EtsTypes.STRING)
    val renderedNumber = identity("Texts", 20, "render_0", EtsTypes.NUMBER, "render")
    val unchanged = identity("Texts", 30, "unchanged", model.symbol.type)
    val methodNumber = identity("OverloadMethods", 20, "choose", EtsTypes.NUMBER, member = true)
    val methodUnique = reserved("OverloadMethods", 30, "choose_0", member = true)
    val methodText = identity("OverloadMethods", 40, "choose_1", EtsTypes.STRING, "choose", member = true)
    val methodPair = pair("OverloadMethods", 50, "choose_2", "choose", member = true)
    val staticNumber = identity("OverloadMethods", 60, "staticSelect", EtsTypes.NUMBER, member = true, static = true)
    val staticText = identity("OverloadMethods", 70, "staticSelect_0", EtsTypes.STRING, "staticSelect", member = true, static = true)
    val service = EtsClass("OverloadMethods", listOf(EtsFunction("constructor", emptyList(), EtsTypes.VOID,
        emptyList(), at("OverloadMethods", 15), kind = EtsFunctionKind.CONSTRUCTOR)) +
        listOf(methodNumber, methodUnique, methodText, methodPair, staticNumber, staticText), at("OverloadMethods"), exported = true)

    fun caller(name: String, offset: Int, declaration: EtsFunction): EtsFunction {
        val source = at("OverloadCalls", offset)
        val values = declaration.parameters.map { parameter(it.symbol.name, it.symbol.type, source) }
        val receiver = if (declaration.kind == EtsFunctionKind.METHOD && !declaration.static)
            parameter("service", service.symbol.type, source) else null
        val calleeSource = at("OverloadCalls", offset + 1)
        val callee = if (declaration.kind == EtsFunctionKind.FUNCTION) EtsReference(declaration.symbol, calleeSource)
            else EtsMember(if (receiver == null) EtsReference(service.symbol, calleeSource) else EtsReference(receiver.symbol),
                declaration.name, declaration.symbol.type, calleeSource, declaration.symbol.id)
        val call = EtsCall(callee, values.map { EtsReference(it.symbol) }, declaration.returnType, at("OverloadCalls", offset + 2))
        return EtsFunction(name, listOfNotNull(receiver) + values, declaration.returnType,
            listOf(EtsReturn(call, at("OverloadCalls", offset + 3))), source, exported = true)
    }
    val calls = listOf(
        caller("callFirst", 10, number), caller("callSecond", 20, secondNumber), caller("callText", 30, text),
        caller("callPair", 40, twoNumbers), caller("callReserved", 50, unique), caller("callUnchanged", 60, unchanged),
        caller("callMemberNumber", 70, methodNumber), caller("callMemberText", 80, methodText),
        caller("callMemberPair", 90, methodPair), caller("callMemberReserved", 100, methodUnique),
        caller("callStaticNumber", 110, staticNumber), caller("callStaticText", 120, staticText),
        caller("callRenderedNumber", 130, renderedNumber))
    return EtsProgram(listOf(
        EtsFile("source/Numbers.kt", listOf(number, secondNumber, twoNumbers, unique)),
        EtsFile("source/Texts.kt", listOf(text, renderedNumber, unchanged)),
        EtsFile(model.source.file!!, listOf(model)), EtsFile(service.source.file!!, listOf(service)),
        EtsFile("source/OverloadCalls.kt", calls)))
}
