package dev.ets

/** Substitution is by declaration identity; a nested function's own binders remain bound. */
fun etsSubstitute(type: EtsType, substitutions: Map<String, EtsType>): EtsType = when (type) {
    is EtsCapturedType -> type.copy(readType = etsSubstitute(type.readType, substitutions), writeType = etsSubstitute(type.writeType, substitutions))
    is EtsTypeParameterType -> substitutions[type.id] ?: type
    is EtsNamedType -> type.copy(arguments = type.arguments.map { etsSubstitute(it, substitutions) })
    is EtsRecordType -> type.copy(fields = type.fields.mapValues { etsSubstitute(it.value, substitutions) })
    is EtsNullableType -> when (val inner = etsSubstitute(type.inner, substitutions)) {
        is EtsNullableType -> inner
        EtsTypes.NULL -> inner
        else -> EtsNullableType(inner)
    }
    is EtsTupleType -> type.copy(elements = type.elements.map { etsSubstitute(it, substitutions) })
    is EtsFunctionType -> {
        val free = substitutions - type.typeParameters.map { it.id }.toSet()
        type.copy(parameters = type.parameters.map { etsSubstitute(it, free) },
            result = etsSubstitute(type.result, free),
            typeParameters = type.typeParameters.map { parameter ->
                parameter.copy(upperBound = parameter.upperBound?.let { etsSubstitute(it, free) })
            })
    }
}

/** Captured arguments remain intervals; only a member's value position is approximated. */
fun etsReadType(type: EtsType, write: Boolean = false): EtsType = when (type) {
    is EtsCapturedType -> if (write) type.writeType else type.readType
    is EtsNullableType -> etsReadType(type.inner, write).let { if (it is EtsNullableType) it else EtsNullableType(it) }
    is EtsFunctionType -> type.copy(parameters = type.parameters.map { etsReadType(it, !write) }, result = etsReadType(type.result, write))
    else -> type
}

fun etsInstantiate(signature: EtsFunctionType, arguments: List<EtsType>): EtsFunctionType {
    require(signature.typeParameters.size == arguments.size) { "Generic target argument count differs from declaration" }
    val substitutions = signature.typeParameters.map { it.id }.zip(arguments).toMap()
    return etsSubstitute(signature.copy(typeParameters = emptyList()), substitutions) as EtsFunctionType
}

/** Recheck the unchanged lambda body against its resolved call-site result type. */
fun etsContextualLambda(value: EtsExpression, expected: EtsType): EtsExpression =
    if (value is EtsLambda && expected is EtsFunctionType &&
        value.parameters.map { it.symbol.type } == expected.parameters)
        value.copy(returnType = expected.result) else value

/** An interval is not the shared existential identity needed by repeated input binders. */
fun etsSupportsCapturedCall(signature: EtsFunctionType, arguments: List<EtsType>): Boolean {
    fun occurrences(type: EtsType, id: String): Int = when (type) {
        is EtsTypeParameterType -> if (type.id == id) 1 else 0
        is EtsNamedType -> type.arguments.sumOf { occurrences(it, id) }
        is EtsNullableType -> occurrences(type.inner, id)
        is EtsCapturedType -> occurrences(type.readType, id) + occurrences(type.writeType, id)
        is EtsFunctionType -> if (type.typeParameters.any { it.id == id }) 0 else
            type.parameters.sumOf { occurrences(it, id) } + occurrences(type.result, id)
        is EtsTupleType -> type.elements.sumOf { occurrences(it, id) }
        is EtsRecordType -> type.fields.values.sumOf { occurrences(it, id) }
    }
    return signature.typeParameters.zip(arguments).all { (parameter, argument) ->
        if (argument !is EtsCapturedType) true else {
            val uses = signature.parameters.filter { occurrences(it, parameter.id) > 0 }
            val container = uses.singleOrNull() as? EtsNamedType
            container != null && container.symbolId != null && !container.external && occurrences(container, parameter.id) == 1
        }
    }
}
