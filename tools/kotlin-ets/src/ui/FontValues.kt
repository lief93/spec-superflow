package dev.ets

private val fontSource = SourceSpan("EtsFontValues.kt", 0, 0)
internal val fontFaceType = etsClassSymbol("EtsFont", fontSource).type as EtsNamedType
internal val fontFamilyType = etsClassSymbol("EtsFontFamily", fontSource).type as EtsNamedType
internal val fontFacesType = EtsNamedType("Array", listOf(fontFaceType))

internal fun fontValueFiles(program: EtsProgram): List<EtsFile> {
    var used = false
    fun type(value: EtsType) {
        when (value) {
            is EtsNamedType -> {
                if (value.symbolId in setOf(fontFaceType.symbolId, fontFamilyType.symbolId)) used = true
                value.arguments.forEach(::type)
            }
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
    if (!used) return emptyList()
    fun valueClass(target: EtsNamedType, properties: Map<String, EtsType>): EtsClass {
        val receiver = EtsReference(EtsSymbol("${target.name}:this", "this", target, fontSource, true))
        val fields = properties.map { (name, type) -> EtsField(EtsSymbol("${target.name}:field:$name", name, type, fontSource), readonly = true) }
        val parameters = properties.map { (name, type) -> EtsParameter(EtsSymbol("${target.name}:param:$name", name, type, fontSource)) }
        val body = fields.zip(parameters).map { (field, parameter) -> EtsExpressionStatement(EtsAssignment(
            EtsMember(receiver, field.symbol.name, field.symbol.type, fontSource, field.symbol.id), EtsReference(parameter.symbol), fontSource)) }
        return EtsClass(target.name, fields + EtsFunction("constructor", parameters, EtsTypes.VOID, body,
            fontSource, kind = EtsFunctionKind.CONSTRUCTOR), fontSource, exported = true)
    }
    return listOf(EtsFile(fontSource.file!!, listOf(
        valueClass(fontFaceType, linkedMapOf("resource" to EtsTypes.STRING, "weight" to EtsTypes.NUMBER, "style" to EtsTypes.NUMBER)),
        valueClass(fontFamilyType, linkedMapOf("fonts" to fontFacesType)))))
}
