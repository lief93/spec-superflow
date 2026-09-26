package dev.ets

private val imageVectorSource = SourceSpan("EtsImageVector.kt", -1, -1)

val etsImageVectorType = etsClassSymbol("EtsImageVector", imageVectorSource).type as EtsNamedType
val etsImageVectorResourceType = EtsNamedType("Resource", external = true)
