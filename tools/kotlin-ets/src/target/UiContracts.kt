package dev.ets

/** Target-owned UI value contracts shared by framework adapters and Harmony output. */
val paddingType = EtsRecordType("Padding", linkedMapOf(
    "left" to EtsTypes.NUMBER,
    "right" to EtsTypes.NUMBER,
    "top" to EtsTypes.NUMBER,
    "bottom" to EtsTypes.NUMBER,
))

val borderStrokeType = EtsRecordType("BorderOptions", linkedMapOf(
    "width" to EtsTypes.NUMBER,
    "color" to EtsTypes.NUMBER,
))

val snackbarHostStateSource = SourceSpan("EtsSnackbarHostState.kt", -1, -1)
val snackbarHostStateType = etsClassSymbol("EtsSnackbarHostState", snackbarHostStateSource).type as EtsNamedType
