package dev.ets

private const val WRAPPED_BUILDER_ID = "arkui:WrappedBuilder"

/** ArkUI's native builder wrapper is an immutable UI-slot descriptor. */
internal fun wrappedBuilderType(parameters: List<EtsType>): EtsNamedType = EtsNamedType(
    "WrappedBuilder", listOf(EtsTupleType(parameters)), symbolId = WRAPPED_BUILDER_ID, external = true)

internal fun isWrappedBuilderType(type: EtsType): Boolean = when (type) {
    is EtsNullableType -> isWrappedBuilderType(type.inner)
    is EtsNamedType -> type.symbolId == WRAPPED_BUILDER_ID
    else -> false
}

internal fun wrappedBuilder(parameters: List<EtsType>, callback: EtsExpression, at: SourceSpan): EtsNew =
    EtsNew(wrappedBuilderType(parameters), listOf(callback), at, repeatableSnapshot = true)
