package dev.ets

fun uiModuleFixture(): EtsProgram {
    fun source(file: String, offset: Int = 10) = SourceSpan(file, offset, offset + 5)
    fun string(value: String, at: SourceSpan) = EtsLiteral(value, EtsTypes.STRING, at)
    fun number(value: Int, at: SourceSpan) = EtsLiteral(value, EtsTypes.NUMBER, at)
    fun invoke(symbol: EtsSymbol, arguments: List<EtsExpression>, at: SourceSpan): EtsCall =
        EtsCall(EtsReference(symbol, at), arguments, (symbol.type as EtsFunctionType).result, at)
    fun external(id: String, name: String, parameters: List<EtsType>, result: EtsType, at: SourceSpan) =
        EtsSymbol(id, name, EtsFunctionType(parameters, result), at, external = true)

    val modelSource = source("TextModel.kt")
    val model = EtsClass("TextModel", listOf(
        EtsField(EtsSymbol("field:text", "text", EtsTypes.STRING, modelSource), string("module", modelSource)),
        EtsFunction("constructor", emptyList(), EtsTypes.VOID, emptyList(), modelSource,
            kind = EtsFunctionKind.CONSTRUCTOR)), modelSource, exported = true)
    val modelType = model.symbol.type as EtsNamedType

    val logicSource = source("CaptionLogic.kt")
    val caption = EtsParameter(EtsSymbol("parameter:caption", "caption", modelType, logicSource))
    val substring = external("stdlib:__etsSubstringFrom", "__etsSubstringFrom",
        listOf(EtsTypes.STRING, EtsTypes.NUMBER), EtsTypes.STRING, logicSource)
    val format = EtsFunction("formatCaption", listOf(caption), EtsTypes.STRING, listOf(EtsReturn(
        invoke(substring, listOf(EtsMember(EtsReference(caption.symbol), "text", EtsTypes.STRING, logicSource),
            number(1, logicSource)), logicSource), logicSource)), logicSource, exported = true)

    val eventSource = source("CaptionEvents.kt")
    val selected = EtsParameter(EtsSymbol("parameter:selected", "selected", modelType, eventSource))
    val logger = EtsReference(EtsSymbol("sdk:hilog", "hilog", EtsNamedType("Hilog"), eventSource, external = true))
    val info = EtsMember(logger, "info", EtsFunctionType(listOf(EtsTypes.NUMBER, EtsTypes.STRING,
        EtsTypes.STRING, EtsTypes.STRING), EtsTypes.VOID), eventSource)
    val record = EtsFunction("recordSelection", listOf(selected), EtsTypes.VOID, listOf(
        EtsExpressionStatement(EtsCall(info, listOf(number(0, eventSource), string("ui-modules", eventSource),
            string("%{public}s", eventSource), EtsMember(EtsReference(selected.symbol), "text", EtsTypes.STRING,
                eventSource)), EtsTypes.VOID, eventSource))), eventSource, exported = true)

    fun component(name: String, file: String, rich: Boolean): EtsClass {
        val at = source(file)
        val parameter = EtsParameter(EtsSymbol("parameter:$file:model", "model", modelType, at),
            EtsNew(modelType, emptyList(), at))
        val text = external("arkui:Text", "Text", listOf(EtsTypes.STRING), EtsTypes.VOID, at)
        fun label(value: EtsExpression): EtsUiElement = EtsUiElement(invoke(text, listOf(value), at))
        val builder = if (rich) {
            val callback = EtsLambda(emptyList(), listOf(EtsExpressionStatement(
                invoke(record.symbol, listOf(EtsReference(parameter.symbol)), at))), EtsTypes.VOID, at)
            val division = external("stdlib:__etsIntDiv", "__etsIntDiv",
                listOf(EtsTypes.NUMBER, EtsTypes.NUMBER), EtsTypes.NUMBER, at)
            val attributes = listOf(
                invoke(external("arkui:fontSize", "fontSize", listOf(EtsTypes.NUMBER), EtsTypes.VOID, at),
                    listOf(invoke(division, listOf(number(48, at), number(2, at)), at)), at),
                invoke(external("arkui:onClick", "onClick", listOf(callback.type), EtsTypes.VOID, at),
                    listOf(callback), at))
            val item = EtsParameter(EtsSymbol("item:$file", "item", modelType, at))
            val repeated = EtsUiForEach(EtsArray(listOf(EtsReference(parameter.symbol)), modelType, at), item,
                listOf(label(invoke(format.symbol, listOf(EtsReference(item.symbol)), at))), at)
            val branches = EtsIf(listOf(
                EtsBranch(EtsLiteral(true, EtsTypes.BOOLEAN, at), listOf(label(
                    invoke(format.symbol, listOf(EtsReference(parameter.symbol)), at)).copy(attributes = attributes))),
                EtsBranch(null, listOf(repeated))), at)
            EtsFunction("Caption", listOf(parameter), EtsTypes.VOID, listOf(branches), at,
                kind = EtsFunctionKind.METHOD, builder = true)
        } else EtsFunction("Caption", emptyList(), EtsTypes.VOID, listOf(label(string("quiet", at))), at,
            kind = EtsFunctionKind.METHOD, builder = true)
        // The existing UI lowering binds its lexical component receiver as an external target symbol.
        val receiver = EtsReference(EtsSymbol("target:this:$file", "this", EtsNamedType(name, external = true), at, true))
        val fields = if (rich) listOf(EtsField(EtsSymbol("field:$file:model", "model", modelType, at),
            EtsNew(modelType, emptyList(), at), state = true)) else emptyList()
        val arguments = if (rich) listOf(EtsMember(receiver, "model", modelType, at)) else emptyList()
        val build = EtsFunction("build", emptyList(), EtsTypes.VOID, listOf(EtsUiElement(EtsCall(
            EtsMember(receiver, builder.name, builder.symbol.type, at), arguments, EtsTypes.VOID, at))),
            source(file, 30), kind = EtsFunctionKind.METHOD, build = true)
        return EtsClass(name, fields + builder + build, at, exported = true, component = true)
    }
    return EtsProgram(listOf(
        EtsFile("TextModel.kt", listOf(model)),
        EtsFile("CaptionLogic.kt", listOf(format)),
        EtsFile("CaptionEvents.kt", listOf(record)),
        EtsFile("CaptionCard.kt", listOf(component("CaptionCard", "CaptionCard.kt", true))),
        EtsFile("QuietCard.kt", listOf(component("QuietCard", "QuietCard.kt", false)))),
        listOf(EtsImport("@ohos.hilog", "hilog", default = true)))
}
