package dev.ets

private val paddingSource = SourceSpan("EtsPadding.kt", 0, 0)
private val horizontalPadding = EtsSymbol("padding:horizontal", "horizontal", EtsTypes.NUMBER, paddingSource)
private val verticalPadding = EtsSymbol("padding:vertical", "vertical", EtsTypes.NUMBER, paddingSource)
private val symmetricPaddingFunction = EtsFunction("__etsSymmetricPadding",
    listOf(EtsParameter(horizontalPadding), EtsParameter(verticalPadding)), paddingType,
    listOf(EtsReturn(EtsObject(linkedMapOf("left" to EtsReference(horizontalPadding),
        "right" to EtsReference(horizontalPadding), "top" to EtsReference(verticalPadding),
        "bottom" to EtsReference(verticalPadding)), paddingType, paddingSource), paddingSource)),
    paddingSource, exported = true)
private val allPadding = EtsSymbol("padding:all", "all", EtsTypes.NUMBER, paddingSource)
private val uniformPaddingFunction = EtsFunction("__etsUniformPadding", listOf(EtsParameter(allPadding)), paddingType,
    listOf(EtsReturn(EtsObject(paddingType.fields.mapValues { EtsReference(allPadding) }, paddingType, paddingSource), paddingSource)),
    paddingSource, exported = true)
private val edgeParameters = listOf("start", "top", "end", "bottom").map {
    EtsParameter(EtsSymbol("padding:edge:$it", it, EtsTypes.NUMBER, paddingSource))
}
private val edgePaddingFunction = EtsFunction("__etsEdgePadding", edgeParameters, paddingType,
    listOf(EtsReturn(EtsObject(linkedMapOf("left" to EtsReference(edgeParameters[0].symbol),
        "right" to EtsReference(edgeParameters[2].symbol), "top" to EtsReference(edgeParameters[1].symbol),
        "bottom" to EtsReference(edgeParameters[3].symbol)), paddingType, paddingSource), paddingSource)), paddingSource, exported = true)

internal fun edgePadding(values: List<EtsExpression>, at: SourceSpan): EtsExpression =
    EtsCall(EtsReference(edgePaddingFunction.symbol, at), values, paddingType, at)

internal fun uniformPadding(value: EtsExpression, at: SourceSpan): EtsExpression =
    EtsCall(EtsReference(uniformPaddingFunction.symbol, at), listOf(value), paddingType, at)

/** One evaluation per source argument even though each value supplies two target edges. */
internal fun symmetricPadding(horizontal: EtsExpression, vertical: EtsExpression, at: SourceSpan): EtsExpression =
    EtsCall(EtsReference(symmetricPaddingFunction.symbol, at), listOf(horizontal, vertical), paddingType, at)

internal fun paddingValueFiles(program: EtsProgram): List<EtsFile> {
    val used = linkedSetOf<EtsFunction>()
    program.files.forEach { file -> file.declarations.forEach { declaration -> walkEts(declaration) { node ->
        if (node is EtsReference) listOf(symmetricPaddingFunction, uniformPaddingFunction, edgePaddingFunction).forEach {
            if (node.symbol.id == it.symbol.id) used += it
        }
    } } }
    return if (used.isNotEmpty()) listOf(EtsFile(paddingSource.file!!, used.toList())) else emptyList()
}
