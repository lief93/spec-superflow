package dev.ets

fun main() {
    val at = SourceSpan("Reactive.kt", 0, 10)
    val string = EtsTypes.STRING
    fun text(value: String) = EtsLiteral(value, string, at)
    fun ui(name: String, arguments: List<EtsExpression>) = EtsUiElement(EtsCall(
        EtsReference(EtsSymbol("native:$name", name, EtsFunctionType(arguments.map { it.type }, EtsTypes.VOID), at, true)),
        arguments, EtsTypes.VOID, at))
    val parameter = EtsParameter(EtsSymbol("Label:value", "value", string, at))
    val leaf = EtsFunction("Label", listOf(parameter), EtsTypes.VOID,
        listOf(ui("Text", listOf(EtsReference(parameter.symbol)))), at, builder = true)
    val forwarded = EtsParameter(EtsSymbol("Forward:value", "value", string, at))
    fun invoke(function: EtsFunction, value: EtsExpression) = EtsUiElement(EtsCall(
        EtsReference(function.symbol), listOf(value), EtsTypes.VOID, at))
    val forward = EtsFunction("Forward", listOf(forwarded), EtsTypes.VOID,
        listOf(invoke(leaf, EtsReference(forwarded.symbol))), at, builder = true)
    val pageSymbol = etsClassSymbol("Page", at)
    val self = EtsReference(EtsSymbol("Page:this", "this", pageSymbol.type, at, true))
    val field = EtsField(EtsSymbol("Page:message", "message", string, at), text("initial"), state = true)
    val state = EtsMember(self, "message", string, at)
    val ordinary = EtsFunction("identity", listOf(EtsParameter(EtsSymbol("identity:x", "x", string, at))),
        string, listOf(EtsReturn(text("constant"), at)), at)
    fun program(argument: EtsExpression = state, label: EtsFunction = leaf): EtsProgram {
        val build = EtsFunction("build", emptyList(), EtsTypes.VOID,
            listOf(invoke(forward, argument)), at, kind = EtsFunctionKind.METHOD, build = true)
        return EtsProgram(listOf(EtsFile("Label.kt", listOf(label, forward, ordinary)),
            EtsFile("Page.kt", listOf(EtsClass("Page", listOf(field, build), at, component = true, entry = true)))))
    }
    val constant = program(text("fixed"))
    check(bindReactiveBuilderArguments(constant) === constant)
    val result = bindReactiveBuilderArguments(program())
    EtsValidator().validate(result)
    val printed = EtsPrinter().program(result)
    check("Label(value: Binding<string>)" in printed)
    check("Forward(value: Binding<string>)" in printed)
    check("Text(value.value)" in printed)
    check("UIUtils.makeBinding" in printed)
    check(result.files.first().declarations.last() == ordinary)
    fun rejected(label: EtsFunction) {
        val error = runCatching { bindReactiveBuilderArguments(program(label = label)) }.exceptionOrNull()
        check(error is Unsupported && error.diagnostic.source == at)
        check("single immediate consumer" in error.message.orEmpty())
    }
    rejected(leaf.copy(body = leaf.body + leaf.body))
    val delayed = EtsLambda(emptyList(), leaf.body, EtsTypes.VOID, at)
    rejected(leaf.copy(body = listOf(ui("Button", listOf(delayed)))))
    val counted = EtsReference(EtsSymbol("counted", "counted", EtsFunctionType(listOf(string), string), at, true))
    val effect = EtsCall(counted, listOf(state), string, at)
    val skipped = leaf.copy(body = listOf(EtsIf(listOf(EtsBranch(EtsLiteral(false, EtsTypes.BOOLEAN, at), leaf.body)), at)))
    fun rejectsEffects(input: EtsProgram) {
        val error = runCatching { bindReactiveBuilderArguments(input) }.exceptionOrNull()
        check(error is Unsupported && "evaluation-preserving" in error.message.orEmpty())
    }
    rejectsEffects(program(effect, skipped))
    val other = EtsParameter(EtsSymbol("Label:other", "other", string, at))
    val reverse = leaf.copy(parameters = listOf(parameter, other), body = listOf(
        ui("Text", listOf(EtsReference(other.symbol))), ui("Text", listOf(EtsReference(parameter.symbol)))))
    val reverseCall = EtsUiElement(EtsCall(EtsReference(reverse.symbol), listOf(effect, effect), EtsTypes.VOID, at))
    val page = program().files.last().declarations.single() as EtsClass
    val build = page.members.filterIsInstance<EtsFunction>().single()
    rejectsEffects(EtsProgram(listOf(EtsFile("Reverse.kt", listOf(reverse, page.copy(members = listOf(field, build.copy(body = listOf(reverseCall)))))))))
    println("PASS reactive builder forwarding, constant and ordinary-function stability, repeated/deferred rejection")
}
