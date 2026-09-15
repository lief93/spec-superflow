package dev.ets

private val paddingSource = SourceSpan("EtsPadding.kt", 0, 0)
private val paddingType = EtsRecordType("Padding", linkedMapOf("left" to EtsTypes.NUMBER,
    "right" to EtsTypes.NUMBER, "top" to EtsTypes.NUMBER, "bottom" to EtsTypes.NUMBER))
private val horizontalPadding = EtsSymbol("padding:horizontal", "horizontal", EtsTypes.NUMBER, paddingSource)
private val verticalPadding = EtsSymbol("padding:vertical", "vertical", EtsTypes.NUMBER, paddingSource)
private val symmetricPaddingFunction = EtsFunction("__etsSymmetricPadding",
    listOf(EtsParameter(horizontalPadding), EtsParameter(verticalPadding)), paddingType,
    listOf(EtsReturn(EtsObject(linkedMapOf("left" to EtsReference(horizontalPadding),
        "right" to EtsReference(horizontalPadding), "top" to EtsReference(verticalPadding),
        "bottom" to EtsReference(verticalPadding)), paddingType, paddingSource), paddingSource)),
    paddingSource, exported = true)

/** One evaluation per source argument even though each value supplies two target edges. */
internal fun symmetricPadding(horizontal: EtsExpression, vertical: EtsExpression, at: SourceSpan): EtsExpression =
    EtsCall(EtsReference(symmetricPaddingFunction.symbol, at), listOf(horizontal, vertical), paddingType, at)

internal fun paddingValueFiles(program: EtsProgram): List<EtsFile> {
    var used = false
    program.files.forEach { file -> file.declarations.forEach { declaration -> walkEts(declaration) { node ->
        if (node is EtsReference && node.symbol.id == symmetricPaddingFunction.symbol.id) used = true
    } } }
    return if (used) listOf(EtsFile(paddingSource.file!!, listOf(symmetricPaddingFunction))) else emptyList()
}
