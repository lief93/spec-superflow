package dev.ets

fun globalBuilderFixture(): EtsProgram {
    fun source(file: String, offset: Int = 10) = SourceSpan("source/$file", offset, offset + 5)
    fun call(symbol: EtsSymbol, values: List<EtsExpression>, at: SourceSpan) =
        EtsCall(EtsReference(symbol, at), values, (symbol.type as EtsFunctionType).result, at)
    fun parameter(id: String, name: String, type: EtsType, at: SourceSpan) =
        EtsParameter(EtsSymbol(id, name, type, at))
    fun arkui(name: String, types: List<EtsType>, at: SourceSpan) =
        EtsSymbol("arkui:$name", name, EtsFunctionType(types, EtsTypes.VOID), at, external = true)

    val modelSource = source("Model.kt")
    val model = EtsClass("LabelModel", listOf(
        EtsField(EtsSymbol("model:text", "text", EtsTypes.STRING, modelSource),
            EtsLiteral("global builder", EtsTypes.STRING, modelSource)),
        EtsFunction("constructor", emptyList(), EtsTypes.VOID, emptyList(), source("Model.kt", 20),
            kind = EtsFunctionKind.CONSTRUCTOR)), modelSource, exported = true)

    val labelsSource = source("Labels.kt")
    val labelModel = parameter("labels:model", "model", model.symbol.type, labelsSource)
    val substring = EtsSymbol("stdlib:__etsSubstringFrom", "__etsSubstringFrom",
        EtsFunctionType(listOf(EtsTypes.STRING, EtsTypes.NUMBER), EtsTypes.STRING), labelsSource, external = true)
    val labelFor = EtsFunction("labelFor", listOf(labelModel), EtsTypes.STRING, listOf(EtsReturn(
        call(substring, listOf(EtsMember(EtsReference(labelModel.symbol), "text", EtsTypes.STRING, labelsSource),
            EtsLiteral(0, EtsTypes.NUMBER, labelsSource)), labelsSource), labelsSource)), labelsSource, exported = true)

    val valuesSource = source("Values.kt")
    val label = parameter("values:label", "label", EtsTypes.STRING, valuesSource)
    val labelLength = EtsFunction("labelLength", listOf(label), EtsTypes.NUMBER, listOf(EtsReturn(
        EtsMember(EtsReference(label.symbol), "length", EtsTypes.NUMBER, valuesSource), valuesSource)),
        valuesSource, exported = true)

    val badgeSource = source("Badge.kt")
    val badgeModel = parameter("badge:model", "model", model.symbol.type, badgeSource)
    val onSelect = parameter("badge:onSelect", "onSelect", EtsFunctionType(emptyList(), EtsTypes.VOID), badgeSource)
    val text = EtsUiElement(call(arkui("Text", listOf(EtsTypes.STRING), badgeSource), listOf(
        call(labelFor.symbol, listOf(EtsReference(badgeModel.symbol)), badgeSource)), badgeSource), attributes = listOf(
        call(arkui("onClick", listOf(onSelect.symbol.type), badgeSource), listOf(EtsReference(onSelect.symbol)), badgeSource)))
    val badge = EtsFunction("Badge", listOf(badgeModel, onSelect), EtsTypes.VOID, listOf(text), badgeSource,
        kind = EtsFunctionKind.FUNCTION, exported = true, builder = true)

    val dashboardSource = source("Dashboard.kt")
    val dashboardModel = parameter("dashboard:model", "model", model.symbol.type, dashboardSource)
    val callback = EtsLambda(emptyList(), listOf(EtsExpressionStatement(call(labelLength.symbol, listOf(
        call(labelFor.symbol, listOf(EtsReference(dashboardModel.symbol)), dashboardSource)), dashboardSource))),
        EtsTypes.VOID, dashboardSource)
    val invocation = EtsUiElement(call(badge.symbol, listOf(EtsReference(dashboardModel.symbol), callback), dashboardSource))
    val column = EtsUiElement(call(arkui("Column", emptyList(), dashboardSource), emptyList(), dashboardSource),
        children = listOf(invocation))
    val dashboard = EtsFunction("Dashboard", listOf(dashboardModel), EtsTypes.VOID, listOf(column), dashboardSource,
        kind = EtsFunctionKind.FUNCTION, exported = true, builder = true)

    return EtsProgram(listOf(model, labelFor, labelLength, badge, dashboard).map { declaration ->
        EtsFile(declaration.source.file!!, listOf(declaration))
    })
}
