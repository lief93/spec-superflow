package dev.ets

internal val imageRequestSource = SourceSpan("EtsImageRequest.kt", 0, 0)
internal val imageRequestType = etsClassSymbol("EtsImageRequest", imageRequestSource).type as EtsNamedType
internal val imageRequestBuilderType = etsClassSymbol("EtsImageRequestBuilder", imageRequestSource).type as EtsNamedType
internal val svgDecoderType = etsClassSymbol("EtsSvgDecoder", imageRequestSource).type as EtsNamedType

internal fun imageRequestValueFiles(program: EtsProgram): List<EtsFile> {
    val types = setOf(imageRequestType, imageRequestBuilderType, svgDecoderType)
    fun uses(type: EtsType): Boolean = when (type) {
        is EtsNamedType -> type in types || type.arguments.any(::uses)
        is EtsNullableType -> uses(type.inner)
        is EtsFunctionType -> type.parameters.any(::uses) || uses(type.result)
        else -> false
    }
    var used = false
    program.files.forEach { file -> file.declarations.forEach { declaration -> walkEts(declaration) { node ->
        if (node is EtsExpression && uses(node.type) || node is EtsFunction && uses(node.symbol.type)) used = true
    } } }
    if (!used) return emptyList()
    val at = imageRequestSource
    val properties = linkedMapOf("requestData" to EtsNullableType(EtsTypes.STRING),
        "crossfadeMillis" to EtsTypes.NUMBER, "decoder" to EtsNullableType(svgDecoderType))
    fun receiver(type: EtsNamedType) = EtsReference(EtsSymbol("${type.name}:this", "this", type, at, true))
    fun field(type: EtsNamedType, name: String) = EtsMember(receiver(type), name, properties.getValue(name), at)
    fun parameter(owner: String, name: String, type: EtsType) = EtsParameter(EtsSymbol("$owner:$name", name, type, at))
    val fields = properties.map { (name, type) -> EtsField(EtsSymbol("imageRequest:$name", name, type, at), readonly = true) }
    val parameters = properties.map { (name, type) -> parameter("request", name, type) }
    val constructor = EtsFunction("constructor", parameters, EtsTypes.VOID, parameters.map { parameter ->
        EtsExpressionStatement(EtsAssignment(field(imageRequestType, parameter.symbol.name), EtsReference(parameter.symbol), at))
    }, at, kind = EtsFunctionKind.CONSTRUCTOR)
    val builderFields = properties.map { (name, type) -> EtsField(EtsSymbol("imageBuilder:$name", name, type, at),
        if (name == "crossfadeMillis") EtsLiteral(0, EtsTypes.NUMBER, at) else EtsLiteral(null, EtsTypes.NULL, at)) }
    fun setter(name: String, target: String, type: EtsType, value: (EtsExpression) -> EtsExpression = { it }): EtsFunction {
        val parameter = parameter(name, "value", type)
        return EtsFunction(name, listOf(parameter), imageRequestBuilderType, listOf(
            EtsExpressionStatement(EtsAssignment(field(imageRequestBuilderType, target), value(EtsReference(parameter.symbol)), at)),
            EtsReturn(receiver(imageRequestBuilderType), at)), at, kind = EtsFunctionKind.METHOD)
    }
    val zero = EtsLiteral(0, EtsTypes.NUMBER, at)
    val builder = EtsClass(imageRequestBuilderType.name, builderFields + listOf(
        EtsFunction("constructor", emptyList(), EtsTypes.VOID, emptyList(), at, kind = EtsFunctionKind.CONSTRUCTOR),
        setter("data", "requestData", EtsNullableType(EtsTypes.STRING)),
        setter("decoderFactory", "decoder", svgDecoderType),
        setter("crossfade", "crossfadeMillis", EtsTypes.NUMBER) { value ->
            EtsConditional(EtsBinary(">", value, zero, EtsTypes.BOOLEAN, at), value, zero, EtsTypes.NUMBER, at)
        },
        EtsFunction("build", emptyList(), imageRequestType, listOf(EtsReturn(EtsNew(imageRequestType,
            properties.keys.map { field(imageRequestBuilderType, it) }, at), at)), at, kind = EtsFunctionKind.METHOD)
    ), at, exported = true)
    return listOf(EtsFile(at.file!!, listOf(
        EtsClass(svgDecoderType.name, listOf(EtsFunction("constructor", emptyList(), EtsTypes.VOID,
            emptyList(), at, kind = EtsFunctionKind.CONSTRUCTOR)), at, exported = true),
        EtsClass(imageRequestType.name, fields + constructor, at, exported = true), builder)))
}
