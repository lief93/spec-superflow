package dev.ets

/** Typed forwarding only; the official common algorithm selects the bridge edges. */
fun etsVirtualBridge(implementation: EtsFunction, receiver: EtsExpression,
    name: String, overrides: List<String>, destination: EtsSymbol = implementation.symbol): EtsFunction {
    val source = implementation.source
    val identity = "<bridge:${implementation.symbol.id}:$name>"
    val parameters = implementation.parameters.map {
        it.copy(symbol = it.symbol.copy(id = "$identity:${it.symbol.id}"), defaultValue = null)
    }
    if (implementation.abstract) return implementation.copy(name = name, parameters = parameters,
        body = emptyList(), overrides = overrides, sourceName = identity)
    val call = EtsCall(EtsMember(receiver, destination.name, destination.type, source, destination.id),
        parameters.map { EtsReference(it.symbol, source) }, implementation.returnType, source,
        implementation.typeParameters.map { EtsTypeParameterType(it.id, it.name) })
    val body = if (implementation.returnType == EtsTypes.VOID) listOf(EtsExpressionStatement(call))
        else listOf(EtsReturn(call, source))
    return implementation.copy(name = name, parameters = parameters, body = body,
        overrides = overrides, sourceName = identity)
}
