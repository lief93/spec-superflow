package dev.ets

/** The pinned runtime base participates in target heritage and constructor validation. */
internal fun exceptionTargetContracts(): Map<String, EtsClass> {
    val at = SourceSpan("<stdlib:Throwable>", 0, 0)
    fun parameter(name: String, type: EtsType) = EtsParameter(EtsSymbol("exception:$name", name, type, at))
    val members = listOf(
        EtsField(EtsSymbol("exception:name", "name", EtsTypes.STRING, at)),
        EtsField(EtsSymbol("exception:message", "message", EtsTypes.STRING, at)),
        EtsField(EtsSymbol("exception:sourceMessage", "sourceMessage", EtsNullableType(EtsTypes.STRING), at), readonly = true),
        EtsFunction("constructor", listOf(parameter("category", EtsTypes.STRING),
            parameter("message", EtsNullableType(EtsTypes.STRING))), EtsTypes.VOID, emptyList(), at,
            kind = EtsFunctionKind.CONSTRUCTOR))
    return mapOf("stdlib:__etsThrowable" to EtsClass("__etsThrowable", members, at))
}

internal val exceptionSupportFunctions = listOf(
    SupportFunction("stdlib:__etsThrowable", """
        class __etsThrowable extends Error {
          readonly sourceMessage: string | null;
          constructor(category: string, message: string | null) {
            super(message === null ? '' : message);
            this.name = category;
            this.sourceMessage = message;
          }
        }
    """.trimIndent()),
    SupportFunction("stdlib:__etsIsFailure", """
        function __etsIsFailure(value: Object | null, category: string): boolean {
          if (!(value instanceof Error)) { return false; }
          let name = value.name;
          while (name !== '') {
            if (name === category) { return true; }
            switch (name) {
        ${exceptionParents.entries.joinToString("\n") { (child, parent) -> "      case '$child': name = '$parent'; break;" }}
              default: return false;
            }
          }
          return false;
        }
    """.trimIndent()),
)
