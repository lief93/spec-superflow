package dev.ets

/** Reuse the accepted source-generic heritage fixture without changing its declarations. */
fun boundedReceiverFixture(): EtsProgram {
    val heritage = genericHeritageFixture()
    val files = heritage.files.filter { file -> file.declarations.all { it is EtsClass } }
    val classes = files.flatMap { it.declarations }.filterIsInstance<EtsClass>().associateBy { it.name }
    fun named(name: String, vararg arguments: EtsType) =
        (classes.getValue(name).symbol.type as EtsNamedType).copy(arguments = arguments.toList())
    fun use(parameter: EtsTypeParameter) = EtsTypeParameterType(parameter.id, parameter.name)
    fun at(file: String, offset: Int) = SourceSpan("source/$file.kt", offset, offset + 5)
    val modelType = named("TokenModel")
    val holderRead = classes.getValue("Holder").members.filterIsInstance<EtsFunction>().single { it.name == "read" }
    val interfaceRead = classes.getValue("Readable").members.filterIsInstance<EtsFunction>().single { it.name == "read" }

    fun function(name: String, parameters: List<EtsTypeParameter>, receiver: EtsTypeParameter, result: EtsType,
        method: EtsFunction?, source: SourceSpan): EtsFunction {
        val reader = EtsParameter(EtsSymbol("parameter:$name:reader", "reader", use(receiver), source))
        val body = if (method == null) emptyList() else listOf(EtsReturn(EtsCall(EtsMember(EtsReference(reader.symbol),
            method.name, EtsFunctionType(emptyList(), result), source, method.symbol.id), emptyList(), result, source), source))
        return EtsFunction(name, listOf(reader), result, body, source, exported = true, typeParameters = parameters)
    }
    val classReceiver = EtsTypeParameter("readClass:R", "R", named("Middle", modelType))
    val interfaceReceiver = EtsTypeParameter("readInterface:R", "R", named("Readable", modelType))
    val value = EtsTypeParameter("readParametric:V", "V")
    val parametricReceiver = EtsTypeParameter("readParametric:R", "R", named("Readable", use(value)))
    val chainParent = EtsTypeParameter("readChain:R", "R", named("Middle", modelType))
    val chainReceiver = EtsTypeParameter("readChain:S", "S", use(chainParent))
    val functions = listOf(
        function("readClass", listOf(classReceiver), classReceiver, modelType, holderRead, at("BoundedCalls", 10)),
        function("readInterface", listOf(interfaceReceiver), interfaceReceiver, modelType, interfaceRead, at("BoundedCalls", 20)),
        function("readParametric", listOf(value, parametricReceiver), parametricReceiver, use(value), interfaceRead, at("BoundedCalls", 30)),
        function("readChain", listOf(chainParent, chainReceiver), chainReceiver, modelType, holderRead, at("BoundedCalls", 40)))

    val boxReceiver = EtsTypeParameter("ReaderBox:R", "R", named("Readable", modelType))
    val boxShell = EtsClass("ReaderBox", emptyList(), at("ReaderBox", 10), exported = true, typeParameters = listOf(boxReceiver))
    val boxType = (boxShell.symbol.type as EtsNamedType).copy(arguments = listOf(use(boxReceiver)))
    val self = EtsReference(EtsSymbol("receiver:ReaderBox", "this", boxType, boxShell.source, external = true))
    val field = EtsSymbol("ReaderBox:reader", "reader", use(boxReceiver), at("ReaderBox", 20))
    val input = EtsParameter(EtsSymbol("ReaderBox:input", "reader", use(boxReceiver), at("ReaderBox", 30)))
    fun fieldReference(source: SourceSpan) = EtsMember(self, field.name, field.type, source, field.id)
    val constructor = EtsFunction("constructor", listOf(input), EtsTypes.VOID, listOf(EtsExpressionStatement(
        EtsAssignment(fieldReference(input.symbol.source), EtsReference(input.symbol), input.symbol.source))),
        input.symbol.source, kind = EtsFunctionKind.CONSTRUCTOR)
    val readSource = at("ReaderBox", 40)
    val read = EtsFunction("read", emptyList(), modelType, listOf(EtsReturn(EtsCall(EtsMember(fieldReference(readSource),
        interfaceRead.name, EtsFunctionType(emptyList(), modelType), readSource, interfaceRead.symbol.id), emptyList(),
        modelType, readSource), readSource)), readSource, kind = EtsFunctionKind.METHOD)
    val box = boxShell.copy(members = listOf(EtsField(field), constructor, read))

    val signatureClass = EtsTypeParameter("acceptClass:R", "R", named("Middle", modelType))
    val signatureInterface = EtsTypeParameter("acceptInterface:R", "R", named("Readable", modelType))
    val signatures = listOf(
        function("acceptClass", listOf(signatureClass), signatureClass, EtsTypes.VOID, null, at("Signatures", 10)),
        function("acceptInterface", listOf(signatureInterface), signatureInterface, EtsTypes.VOID, null, at("Signatures", 20)))
    return EtsProgram(files + listOf(EtsFile("source/BoundedCalls.kt", functions), EtsFile("source/ReaderBox.kt", listOf(box)),
        EtsFile("source/Signatures.kt", signatures)))
}
