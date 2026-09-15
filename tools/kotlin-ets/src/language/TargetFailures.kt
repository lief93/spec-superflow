package dev.ets

internal val targetErrorType = EtsNamedType("__etsThrowable", symbolId = "stdlib:__etsThrowable", external = true)

/** Native Error carries a stable category independently of its platform stack/message. */
internal fun namedTargetFailure(category: String, at: SourceSpan, message: EtsExpression = EtsLiteral(category, EtsTypes.STRING, at)): EtsExpression {
    return EtsNew(targetErrorType, listOf(EtsLiteral(category, EtsTypes.STRING, at), message), at)
}
