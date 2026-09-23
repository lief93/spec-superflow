package dev.ets

fun main() {
    val at = SourceSpan("ContextBindingProbe.kt", 12, 24)
    fun value(id: String, type: EtsType) = EtsReference(EtsSymbol(id, id, type, at, external = true))
    val composition = value("composition", compositionContextType)
    val material = value("material", materialContextType)
    val contracts = listOf(
        ImplicitContextContract(COMPOSITION_CONTEXT, "composition", compositionContextType),
        ImplicitContextContract(MATERIAL_CONTEXT, "material", materialContextType),
    )
    val reverseInsertion = linkedMapOf(MATERIAL_CONTEXT to material, COMPOSITION_CONTEXT to composition)
    check(bindImplicitContextArguments(contracts, reverseInsertion, emptyMap(), at) ==
        listOf(composition, material))

    val missing = runCatching {
        bindImplicitContextArguments(contracts, mapOf(MATERIAL_CONTEXT to material), emptyMap(), at)
    }.exceptionOrNull()
    check(missing is InvalidTarget && missing.source == at &&
        "Missing implicit context $COMPOSITION_CONTEXT" in missing.message.orEmpty() &&
        compositionContextType.toString() in missing.message.orEmpty())

    val wrong = runCatching {
        bindImplicitContextArguments(contracts,
            mapOf(COMPOSITION_CONTEXT to value("wrong", EtsTypes.STRING), MATERIAL_CONTEXT to material),
            emptyMap(), at)
    }.exceptionOrNull()
    check(wrong is InvalidTarget && wrong.source == at &&
        EtsTypes.STRING.toString() in wrong.message.orEmpty() &&
        compositionContextType.toString() in wrong.message.orEmpty())

    val wrongShapes = runCatching {
        newMaterialContext(at,
            MaterialContextField.COLOR_SCHEME to value("scheme", materialColorSchemeType),
            MaterialContextField.CONTENT_COLOR to value("contentColor", EtsTypes.NUMBER),
            MaterialContextField.TYPOGRAPHY to value("typography", typographyType),
            MaterialContextField.TEXT_STYLE to value("style", textStyleType),
            MaterialContextField.SHAPES to value("wrongShapes", textStyleType))
    }.exceptionOrNull()
    check(wrongShapes is InvalidTarget && wrongShapes.source == at &&
        "Material context shapes" in wrongShapes.message.orEmpty() &&
        textStyleType.toString() in wrongShapes.message.orEmpty() &&
        materialShapesType.toString() in wrongShapes.message.orEmpty())
    println("PASS identity-ordered implicit contexts and source-linked missing/wrong-type rejection")
}
