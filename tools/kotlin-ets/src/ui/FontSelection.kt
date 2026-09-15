package dev.ets

private val fontSelectionSource = SourceSpan("EtsFontSelection.kt", 0, 0)
private val scoreFont = fontScoreFunction()
private val selectFont = fontSelectionFunction()
private val registerFont = fontRegistrationFunction()

internal fun nativeFontFamily(family: EtsExpression, weight: EtsExpression, style: EtsExpression, at: SourceSpan): EtsExpression =
    EtsCall(EtsReference(registerFont.symbol, at), listOf(family, weight, style), EtsTypes.STRING, at)

private fun references(program: EtsProgram, id: String): Boolean {
    var found = false
    program.files.forEach { file -> file.declarations.forEach { declaration -> walkEts(declaration) { node ->
        if (node is EtsReference && node.symbol.id == id) found = true
    } } }
    return found
}
internal fun fontSelectionFiles(program: EtsProgram): List<EtsFile> =
    if (references(program, registerFont.symbol.id)) listOf(EtsFile(fontSelectionSource.file!!, listOf(scoreFont, selectFont, registerFont))) else emptyList()

internal fun fontSelectionImports(program: EtsProgram): List<EtsImport> =
    if (references(program, "arkui:font-api")) listOf(EtsImport("@ohos.font", "font", "__etsFontApi", default = true)) else emptyList()

/** AndroidX FontMatcher's CSS ordering; style matching takes priority, and ties keep source order. */
private fun fontScoreFunction(): EtsFunction {
    val at = fontSelectionSource
    fun parameter(name: String, type: EtsType) = EtsParameter(EtsSymbol("fontScore:$name", name, type, at))
    val parameters = listOf(parameter("font", fontFaceType), parameter("weight", EtsTypes.NUMBER), parameter("style", EtsTypes.NUMBER))
    val font = EtsReference(parameters[0].symbol)
    val weight = EtsReference(parameters[1].symbol)
    val style = EtsReference(parameters[2].symbol)
    val candidate = EtsMember(font, "weight", EtsTypes.NUMBER, at)
    fun n(value: Int) = EtsLiteral(value, EtsTypes.NUMBER, at)
    fun b(op: String, l: EtsExpression, r: EtsExpression, type: EtsType = EtsTypes.NUMBER) = EtsBinary(op, l, r, type, at)
    fun condition(op: String, l: EtsExpression, r: EtsExpression) = b(op, l, r, EtsTypes.BOOLEAN)
    fun choose(test: EtsExpression, yes: EtsExpression, no: EtsExpression) = EtsConditional(test, yes, no, EtsTypes.NUMBER, at)
    val below = b("-", weight, candidate)
    val above = b("-", candidate, weight)
    val low = choose(condition("<=", candidate, weight), below, b("+", n(1000), above))
    val high = choose(condition(">=", candidate, weight), above, b("+", n(1000), below))
    val middle = choose(b("&&", condition(">=", candidate, weight), condition("<=", candidate, n(500)), EtsTypes.BOOLEAN),
        above, choose(condition("<", candidate, weight), b("+", n(1000), below), b("+", n(2000), above)))
    val distance = choose(condition("<", weight, n(400)), low, choose(condition(">", weight, n(500)), high, middle))
    val penalty = choose(condition("===", EtsMember(font, "style", EtsTypes.NUMBER, at), style), n(0), n(10000))
    return EtsFunction("__etsFontScore", parameters, EtsTypes.NUMBER, listOf(EtsReturn(b("+", penalty, distance), at)), at, exported = true)
}

private fun fontSelectionFunction(): EtsFunction {
    val at = fontSelectionSource
    fun symbol(name: String, type: EtsType) = EtsSymbol("fontSelect:$name", name, type, at)
    val parameters = listOf(EtsParameter(symbol("family", fontFamilyType)), EtsParameter(symbol("weight", EtsTypes.NUMBER)), EtsParameter(symbol("style", EtsTypes.NUMBER)))
    val fonts = EtsMember(EtsReference(parameters[0].symbol), "fonts", fontFacesType, at)
    val first = EtsCall(EtsReference(EtsSymbol("stdlib:__etsListGet", "__etsListGet", EtsFunctionType(listOf(fontFacesType, EtsTypes.NUMBER), fontFaceType), at, true)),
        listOf(fonts, EtsLiteral(0, EtsTypes.NUMBER, at)), fontFaceType, at, listOf(fontFaceType))
    val selected = symbol("selected", fontFaceType)
    val best = symbol("best", EtsTypes.NUMBER)
    fun score(value: EtsExpression) = EtsCall(EtsReference(scoreFont.symbol), listOf(value, EtsReference(parameters[1].symbol), EtsReference(parameters[2].symbol)), EtsTypes.NUMBER, at)
    val candidate = symbol("candidate", fontFaceType)
    val distance = symbol("distance", EtsTypes.NUMBER)
    fun assign(target: EtsSymbol, value: EtsExpression) = EtsExpressionStatement(EtsAssignment(EtsReference(target), value, at))
    val callback = EtsLambda(listOf(EtsParameter(candidate)), listOf(EtsVariable(distance, score(EtsReference(candidate)), false),
        EtsIf(listOf(EtsBranch(EtsBinary("<", EtsReference(distance), EtsReference(best), EtsTypes.BOOLEAN, at),
            listOf(assign(selected, EtsReference(candidate)), assign(best, EtsReference(distance))))), at)), EtsTypes.VOID, at)
    val iterate = EtsCall(EtsMember(fonts, "forEach", EtsFunctionType(listOf(callback.type), EtsTypes.VOID), at), listOf(callback), EtsTypes.VOID, at)
    return EtsFunction("__etsSelectFont", parameters, fontFaceType, listOf(EtsVariable(selected, first, true),
        EtsVariable(best, score(EtsReference(selected)), true), EtsExpressionStatement(iterate), EtsReturn(EtsReference(selected), at)), at, exported = true)
}

private fun fontRegistrationFunction(): EtsFunction {
    val at = fontSelectionSource
    val parameters = selectFont.parameters.map { EtsParameter(it.symbol.copy(id = "fontRegister:${it.symbol.name}")) }
    val font = EtsSymbol("fontRegister:font", "font", fontFaceType, at)
    val name = EtsMember(EtsReference(font), "resource", EtsTypes.STRING, at)
    val resourceType = EtsNamedType("Resource", external = true)
    val resource = EtsCall(EtsReference(EtsSymbol("arkui:rawfile", "\$rawfile", EtsFunctionType(listOf(EtsTypes.STRING), resourceType), at, true)), listOf(name), resourceType, at)
    val optionsType = EtsRecordType("EtsFontOptions", linkedMapOf("familyName" to EtsTypes.STRING, "familySrc" to resourceType))
    val options = EtsObject(linkedMapOf("familyName" to name, "familySrc" to resource), optionsType, at)
    val api = EtsReference(EtsSymbol("arkui:font-api", "__etsFontApi", EtsNamedType("FontApi", external = true), at, true))
    val register = EtsCall(EtsMember(api, "registerFont", EtsFunctionType(listOf(optionsType), EtsTypes.VOID), at), listOf(options), EtsTypes.VOID, at)
    return EtsFunction("__etsFontFamilyName", parameters, EtsTypes.STRING, listOf(
        EtsVariable(font, EtsCall(EtsReference(selectFont.symbol), parameters.map { EtsReference(it.symbol) }, fontFaceType, at), false),
        EtsExpressionStatement(register), EtsReturn(name, at)), at, exported = true)
}
