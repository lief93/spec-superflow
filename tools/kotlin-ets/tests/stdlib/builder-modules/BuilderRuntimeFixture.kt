package dev.ets.tests.builderruntime

import dev.ets.*

data class BuilderRuntimeFixture(
    val program: EtsProgram,
    val ordinaryProgram: EtsProgram,
    val countSymbol: EtsSymbol,
    val summary: EtsFunction,
    val captions: EtsFunction,
    val actions: EtsFunction,
)

fun builderRuntimeFixture(countOverride: EtsSymbol? = null, uiInCallback: Boolean = false): BuilderRuntimeFixture {
    fun at(file: String, offset: Int = 10) = SourceSpan(file, offset, offset + 5)
    fun number(value: Int, source: SourceSpan) = EtsLiteral(value, EtsTypes.NUMBER, source)
    fun string(value: String, source: SourceSpan) = EtsLiteral(value, EtsTypes.STRING, source)
    fun external(id: String, name: String, parameters: List<EtsType>, result: EtsType, source: SourceSpan) =
        EtsSymbol(id, name, EtsFunctionType(parameters, result), source, external = true)
    fun invoke(symbol: EtsSymbol, values: List<EtsExpression>, source: SourceSpan,
        types: List<EtsType> = emptyList()) = EtsCall(EtsReference(symbol, source), values,
        (symbol.type as EtsFunctionType).result, source, types)
    fun helper(name: String, values: List<EtsExpression>, result: EtsType, source: SourceSpan,
        types: List<EtsType> = emptyList()) = invoke(external("stdlib:$name", name, values.map { it.type }, result, source),
        values, source, types)
    fun ui(name: String, values: List<EtsExpression>, source: SourceSpan) =
        invoke(external("arkui:$name", name, values.map { it.type }, EtsTypes.VOID, source), values, source)

    val captionsAt = at("RuntimeCaptions.kt")
    val captionText = EtsParameter(EtsSymbol("parameter:caption:text", "text", EtsTypes.STRING, captionsAt))
    val captions = EtsFunction("captionForRuntime", listOf(captionText), EtsTypes.STRING, listOf(EtsReturn(
        helper("__etsSubstring", listOf(EtsReference(captionText.symbol), number(0, captionsAt), number(3, captionsAt)),
            EtsTypes.STRING, captionsAt), captionsAt)), captionsAt, exported = true)

    val actionsAt = at("RuntimeActions.kt")
    val actionValue = EtsParameter(EtsSymbol("parameter:action:value", "value", EtsTypes.NUMBER, actionsAt))
    val actions = EtsFunction("onRuntimeMetric", listOf(actionValue), EtsTypes.NUMBER, listOf(EtsReturn(
        helper("__etsIntRem", listOf(EtsReference(actionValue.symbol), number(7, actionsAt)), EtsTypes.NUMBER, actionsAt),
        actionsAt)), actionsAt, exported = true)

    val source = at("RuntimeSummary.kt")
    val arrayType = EtsNamedType("Array", listOf(EtsTypes.NUMBER))
    val label = EtsParameter(EtsSymbol("parameter:summary:label", "label", EtsTypes.STRING, source))
    val values = EtsParameter(EtsSymbol("parameter:summary:values", "values", arrayType, source))
    val expanded = EtsParameter(EtsSymbol("parameter:summary:expanded", "expanded", EtsTypes.BOOLEAN, source))
    fun positive(id: String): EtsLambda {
        val item = EtsParameter(EtsSymbol("predicate:$id", "item", EtsTypes.NUMBER, source))
        return EtsLambda(listOf(item), listOf(EtsReturn(EtsBinary(">", EtsReference(item.symbol), number(0, source),
            EtsTypes.BOOLEAN, source), source)), EtsTypes.BOOLEAN, source)
    }
    val filtered = helper("__etsListFilter", listOf(EtsReference(values.symbol), positive("filter"),
        EtsLiteral(true, EtsTypes.BOOLEAN, source)), arrayType, source, listOf(EtsTypes.NUMBER))
    val predicate = positive("count")
    val countSymbol = external("stdlib:__etsListCount", "__etsListCount", listOf(arrayType, predicate.type), EtsTypes.NUMBER, source)
    val count = invoke(countOverride ?: countSymbol, listOf(filtered, predicate), source, listOf(EtsTypes.NUMBER))
    val callbackBody = listOf<EtsStatement>(EtsExpressionStatement(invoke(actions.symbol, listOf(count), source))) +
        if (uiInCallback) listOf(EtsUiElement(ui("Text", listOf(string("invalid callback UI", source)), source))) else emptyList()
    val callback = EtsLambda(emptyList(), callbackBody, EtsTypes.VOID, source)
    val textValue = helper("__etsSubstringFrom", listOf(invoke(captions.symbol, listOf(EtsReference(label.symbol)), source),
        number(1, source)), EtsTypes.STRING, source)
    val fontSize = helper("__etsIntDiv", listOf(number(48, source), number(2, source)), EtsTypes.NUMBER, source)
    val paddingType = EtsRecordType("Padding", linkedMapOf("left" to EtsTypes.NUMBER))
    val padding = EtsObject(linkedMapOf("left" to fontSize), paddingType, source)
    val heading = EtsUiElement(ui("Text", listOf(textValue), source), attributes = listOf(
        ui("fontSize", listOf(fontSize), source), ui("padding", listOf(padding), source),
        ui("onClick", listOf(callback), source)))
    val item = EtsParameter(EtsSymbol("summary:foreach:item", "item", EtsTypes.NUMBER, source))
    val itemText = EtsCall(EtsMember(EtsReference(item.symbol), "toString", EtsFunctionType(emptyList(), EtsTypes.STRING), source),
        emptyList(), EtsTypes.STRING, source)
    val repeated = EtsUiForEach(filtered, item, listOf(EtsUiElement(ui("Text", listOf(itemText), source))), source)
    val conditional = EtsIf(listOf(EtsBranch(EtsReference(expanded.symbol), listOf(heading)),
        EtsBranch(null, listOf(repeated))), source)
    val summary = EtsFunction("renderRuntimeSummary", listOf(label, values, expanded), EtsTypes.VOID,
        listOf(EtsUiElement(ui("Column", emptyList(), source), children = listOf(conditional))), source,
        exported = true, builder = true)

    val quietAt = at("RuntimeQuiet.kt")
    val quiet = EtsFunction("renderRuntimeQuiet", emptyList(), EtsTypes.VOID, listOf(EtsUiElement(
        ui("Text", listOf(string("__etsIntDiv __etsListAny __etsMissing", quietAt)), quietAt))), quietAt,
        exported = true, builder = true)
    val pageAt = at("RuntimeBuilderPage.kt")
    val build = EtsFunction("build", emptyList(), EtsTypes.VOID, listOf(
        EtsUiElement(ui("Column", emptyList(), pageAt), children = listOf(
            EtsUiElement(invoke(summary.symbol, listOf(string("metrics", pageAt),
                EtsArray(listOf(number(1, pageAt), number(-2, pageAt), number(3, pageAt)), EtsTypes.NUMBER, pageAt),
                EtsLiteral(true, EtsTypes.BOOLEAN, pageAt)), pageAt)),
            EtsUiElement(invoke(quiet.symbol, emptyList(), pageAt))))), pageAt,
        kind = EtsFunctionKind.METHOD, build = true)
    val page = EtsClass("RuntimeBuilderPage", listOf(build), pageAt, exported = true, component = true)
    val program = EtsProgram(listOf(EtsFile("RuntimeCaptions.kt", listOf(captions)),
        EtsFile("RuntimeActions.kt", listOf(actions)), EtsFile("RuntimeSummary.kt", listOf(summary)),
        EtsFile("RuntimeQuiet.kt", listOf(quiet)), EtsFile("RuntimeBuilderPage.kt", listOf(page))))

    // The same value/callback nodes in an ordinary function must select the same runtime.
    val ordinary = summary.copy(builder = false, body = listOf(textValue, fontSize, padding, callback, filtered)
        .map(::EtsExpressionStatement))
    val ordinaryProgram = EtsProgram(program.files.filter { it.sourcePath in
        setOf("RuntimeCaptions.kt", "RuntimeActions.kt", "RuntimeSummary.kt") }.map { file ->
        if (file.sourcePath == "RuntimeSummary.kt") file.copy(declarations = listOf(ordinary)) else file
    })
    return BuilderRuntimeFixture(program, ordinaryProgram, countSymbol, summary, captions, actions)
}
