package dev.ets

internal val targetErrorType = EtsNamedType("Error", external = true)

/** Native Error carries a stable category independently of its platform stack/message. */
internal fun namedTargetFailure(category: String, at: SourceSpan, message: EtsExpression = EtsLiteral(category, EtsTypes.STRING, at)): EtsExpression {
    val error = EtsSymbol("error:${at.file}:${at.start}:$category", "__etsError", targetErrorType, at)
    return EtsCall(EtsLambda(emptyList(), listOf(
        EtsVariable(error, EtsNew(targetErrorType, listOf(message), at), false),
        EtsExpressionStatement(EtsAssignment(EtsMember(EtsReference(error), "name", EtsTypes.STRING, at),
            EtsLiteral(category, EtsTypes.STRING, at), at)),
        EtsReturn(EtsReference(error), at)), targetErrorType, at), emptyList(), targetErrorType, at)
}
