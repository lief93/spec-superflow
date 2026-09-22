package dev.ets

internal val textStyleSource = SourceSpan("EtsTextStyle.kt", 0, 0)
internal val textStyleType = etsClassSymbol("EtsTextStyle", textStyleSource).type as EtsNamedType
private val textStyleMerge = etsFunctionSymbol("__etsMergeTextStyle",
    listOf(textStyleType, textStyleType), textStyleType, textStyleSource)
internal val textStyleFields = linkedMapOf("color" to EtsTypes.NUMBER, "fontSize" to EtsTypes.NUMBER,
    "fontWeight" to EtsTypes.NUMBER, "fontStyle" to EtsTypes.NUMBER, "fontFamily" to fontFamilyType,
    "letterSpacing" to EtsTypes.NUMBER, "textDecoration" to textDecorationType,
    "textAlign" to EtsNamedType("TextAlign"), "lineHeight" to EtsTypes.NUMBER)

internal fun mergeTextStyles(inherited: EtsExpression, provided: EtsExpression, at: SourceSpan): EtsExpression =
    EtsCall(EtsReference(textStyleMerge, at), listOf(inherited, provided), textStyleType, at)

internal fun textStyleFile(): EtsFile {
    val at = textStyleSource
    val receiver = EtsReference(EtsSymbol("textStyle:this", "this", textStyleType, at, true))
    val fields = textStyleFields.map { (name, type) ->
        EtsField(EtsSymbol("textStyle:field:$name", name, EtsNullableType(type), at), readonly = true)
    }
    val parameters = fields.map { EtsParameter(it.symbol.copy(id = "textStyle:param:${it.symbol.name}")) }
    val body = fields.zip(parameters).map { (field, parameter) -> EtsExpressionStatement(EtsAssignment(
        EtsMember(receiver, field.symbol.name, field.symbol.type, at, field.symbol.id), EtsReference(parameter.symbol), at)) }
    val type = EtsClass(textStyleType.name, fields + EtsFunction("constructor",
        parameters, EtsTypes.VOID, body, at, kind = EtsFunctionKind.CONSTRUCTOR), at, exported = true)
    val inherited = EtsParameter(EtsSymbol("textStyle:merge:inherited", "inherited", textStyleType, at))
    val provided = EtsParameter(EtsSymbol("textStyle:merge:provided", "provided", textStyleType, at))
    val merged = EtsNew(textStyleType, fields.map { field ->
        val nullable = field.symbol.type
        EtsBinary("??", EtsMember(EtsReference(provided.symbol), field.symbol.name, nullable, at, field.symbol.id),
            EtsMember(EtsReference(inherited.symbol), field.symbol.name, nullable, at, field.symbol.id), nullable, at)
    }, at)
    val merge = EtsFunction(textStyleMerge.name, listOf(inherited, provided), textStyleType,
        listOf(EtsReturn(merged, at)), at, exported = true)
    return EtsFile(at.file!!, listOf(type, merge))
}

internal fun usesTextStyle(program: EtsProgram): Boolean {
    var used = false
    fun type(value: EtsType) {
        when (value) {
            is EtsNamedType -> { if (value.symbolId == textStyleType.symbolId) used = true; value.arguments.forEach(::type) }
            is EtsNullableType -> type(value.inner)
            is EtsFunctionType -> { value.parameters.forEach(::type); type(value.result) }
            is EtsRecordType -> value.fields.values.forEach(::type)
            is EtsTupleType -> value.elements.forEach(::type)
            is EtsCapturedType -> { type(value.readType); type(value.writeType) }
            is EtsTypeParameterType -> Unit
        }
    }
    program.files.forEach { file -> file.declarations.forEach { declaration -> walkEts(declaration) { node ->
        if (node is EtsExpression) type(node.type)
        when (node) {
            is EtsFunction -> type(node.symbol.type)
            is EtsField -> type(node.symbol.type)
            is EtsGlobal -> type(node.symbol.type)
            is EtsVariable -> type(node.symbol.type)
            else -> Unit
        }
    } } }
    return used
}
