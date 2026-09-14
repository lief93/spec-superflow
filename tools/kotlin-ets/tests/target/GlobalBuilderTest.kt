package dev.ets

fun checkGlobalBuilderContract() {
    val source = SourceSpan("Label.kt", 10, 40)
    val text = EtsParameter(EtsSymbol("label:text", "text", EtsTypes.STRING, source))
    val native = EtsSymbol("arkui:Text", "Text", EtsFunctionType(listOf(EtsTypes.STRING), EtsTypes.VOID), source, external = true)
    val label = EtsFunction("Label", listOf(text), EtsTypes.VOID,
        listOf(EtsUiElement(EtsCall(EtsReference(native), listOf(EtsReference(text.symbol)), EtsTypes.VOID, source))),
        source, exported = true, builder = true)
    val pageSource = SourceSpan("Page.kt", 0, 20)
    val invocation = EtsCall(EtsReference(label.symbol), listOf(EtsLiteral("Ready", EtsTypes.STRING, source)), EtsTypes.VOID, source)
    val build = EtsFunction("build", emptyList(), EtsTypes.VOID, listOf(EtsUiElement(invocation)), pageSource,
        kind = EtsFunctionKind.METHOD, build = true)
    val page = EtsClass("Page", listOf(build), pageSource, component = true, entry = true)
    fun program(function: EtsFunction = label, component: EtsClass = page) =
        EtsProgram(listOf(EtsFile("Label.kt", listOf(function)), EtsFile("Page.kt", listOf(component))))
    val code = EtsPrinter().program(program())
    check("@Builder\nexport function Label(text: string)" in code)
    check("Label(\"Ready\")" in code)
    check("renderLabel" !in code && "this.Label" !in code)
    fun rejected(value: EtsProgram) {
        val error = runCatching { EtsValidator().validate(value) }.exceptionOrNull()
        check(error is InvalidTarget) { "Invalid global builder contract must fail: $value" }
    }
    listOf(
        label.copy(returnType = EtsTypes.NUMBER),
        label.copy(static = true),
        label.copy(private = true),
        label.copy(kind = EtsFunctionKind.METHOD),
        label.copy(build = true),
        label.copy(builder = false),
    ).forEach { rejected(program(it)) }
    val wrongArgument = invocation.copy(arguments = listOf(EtsLiteral(1, EtsTypes.NUMBER, source)))
    rejected(program(component = page.copy(members = listOf(build.copy(body = listOf(EtsUiElement(wrongArgument)))))))
    val unbound = invocation.copy(callee = EtsReference(label.symbol.copy(id = "missing:Label")))
    rejected(program(component = page.copy(members = listOf(build.copy(body = listOf(EtsUiElement(unbound)))))))
    val fakeThis = EtsReference(EtsSymbol("ui:this", "this", page.symbol.type, source, external = true))
    rejected(program(label.copy(body = listOf(EtsUiElement(EtsCall(EtsMember(fakeThis, "build", build.symbol.type, source), emptyList(), EtsTypes.VOID, source))))))
    val ordinary = label.copy(builder = false, body = emptyList())
    rejected(program(ordinary))
    val ordinaryCaller = EtsFunction("run", emptyList(), EtsTypes.VOID, listOf(EtsExpressionStatement(invocation)), pageSource)
    rejected(EtsProgram(listOf(EtsFile("Label.kt", listOf(label, ordinaryCaller)))))
    val callback = EtsLambda(emptyList(), listOf(EtsExpressionStatement(invocation)), EtsTypes.VOID, source)
    val event = EtsSymbol("arkui:onClick", "onClick", EtsFunctionType(listOf(callback.type), EtsTypes.VOID), source, external = true)
    rejected(program(component = page.copy(members = listOf(build.copy(body = listOf(EtsUiElement(invocation,
        attributes = listOf(EtsCall(EtsReference(event), listOf(callback), EtsTypes.VOID, source)))))))))
    println("Global builder target contract: positive and 12 rejection cases passed")
}
