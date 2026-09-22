package dev.ets

fun checkReactiveStateContract() {
    val at = SourceSpan("ReactiveState.ets", 1, 40)
    fun number(value: Int) = EtsLiteral(value, EtsTypes.NUMBER, at)
    fun text(value: String) = EtsLiteral(value, EtsTypes.STRING, at)
    val pageShell = EtsClass("ReactiveStatePage", emptyList(), at, component = true, entry = true)
    val self = EtsReference(EtsSymbol("reactive:this", "this", pageShell.symbol.type, at, external = true))
    val count = EtsField(EtsSymbol("reactive:count", "count", EtsTypes.NUMBER, at), number(0),
        visibility = EtsVisibility.PRIVATE, state = true)
    val countValue = EtsMember(self, count.symbol.name, count.symbol.type, at, count.symbol.id)
    val update = EtsAssignment(countValue,
        EtsBinary("+", countValue, number(1), EtsTypes.NUMBER, at), at)
    val callback = EtsLambda(emptyList(), listOf(EtsExpressionStatement(update)), EtsTypes.VOID, at)
    fun native(name: String, arguments: List<EtsExpression> = emptyList(), children: List<EtsStatement>? = null) =
        EtsUiElement(EtsCall(EtsReference(EtsSymbol("arkui:$name", name,
            EtsFunctionType(arguments.map { it.type }, EtsTypes.VOID), at, external = true)),
            arguments, EtsTypes.VOID, at), children)
    val click = EtsCall(EtsReference(EtsSymbol("arkui:onClick", "onClick",
        EtsFunctionType(listOf(callback.type), EtsTypes.VOID), at, external = true)),
        listOf(callback), EtsTypes.VOID, at)
    val build = EtsFunction("build", emptyList(), EtsTypes.VOID, listOf(native("Column", children = listOf(
        native("Text", listOf(EtsBinary("+", text("count="), countValue, EtsTypes.STRING, at))),
        native("Button", listOf(text("Update"))).copy(attributes = listOf(click)),
    ))), at, kind = EtsFunctionKind.METHOD, build = true)
    val page = pageShell.copy(members = listOf(count, build))
    fun program(declaration: EtsClass = page, extra: List<EtsDeclaration> = emptyList()) =
        EtsProgram(listOf(EtsFile(at.file!!, listOf(declaration) + extra)))
    val code = EtsPrinter().program(program())
    check("@State private count: number = 0;" in code)
    check("Text(\"count=\" + this.count)" in code)
    check("this.count = this.count + 1;" in code)
    val nodes = mutableListOf<EtsNode>()
    walkEts(page, nodes::add)
    check(nodes.filterIsInstance<EtsMember>().any { it.symbolId == count.symbol.id && it.type == EtsTypes.NUMBER })
    check(nodes.filterIsInstance<EtsAssignment>().single().target == countValue)

    fun rejected(declaration: EtsClass = page, extra: List<EtsDeclaration> = emptyList(), message: String) {
        val failure = runCatching { EtsValidator().validate(program(declaration, extra)) }.exceptionOrNull()
        check(failure is InvalidTarget && message in failure.message.orEmpty()) { "Expected $message, got $failure" }
    }
    rejected(page.copy(members = listOf(count.copy(initializer = text("wrong")), build)), message = "type")
    val badUpdate = update.copy(value = text("wrong"))
    val badCallback = callback.copy(body = listOf(EtsExpressionStatement(badUpdate)))
    val badClick = click.copy(arguments = listOf(badCallback))
    val badBuild = build.copy(body = listOf(native("Button", listOf(text("Bad"))).copy(attributes = listOf(badClick))))
    rejected(page.copy(members = listOf(count, badBuild)), message = "type")
    rejected(page.copy(members = listOf(count.copy(initializer = null), build)), message = "initialized")
    rejected(page.copy(members = listOf(count.copy(readonly = true), build)), message = "mutable")
    rejected(page.copy(component = false, entry = false), message = "component instance")
    rejected(page.copy(members = listOf(count.copy(static = true), build)), message = "component instance")

    val foreignAt = SourceSpan("Foreign.ets", 1, 20)
    val pageParameter = EtsParameter(EtsSymbol("foreign:page", "page", page.symbol.type, foreignAt))
    val foreignRead = EtsMember(EtsReference(pageParameter.symbol), count.symbol.name, count.symbol.type,
        foreignAt, count.symbol.id)
    val foreign = EtsFunction("foreignRead", listOf(pageParameter), EtsTypes.NUMBER,
        listOf(EtsReturn(foreignRead, foreignAt)), foreignAt, exported = true)
    rejected(extra = listOf(foreign), message = "owning component")

    System.getenv("KOTLIN_ETS_REACTIVE_STATE_FIXTURE")?.let { java.io.File(it).writeText(code) }
    println("Reactive state target contract: declaration/read/update, exact types and six scope/shape rejections passed")
}
