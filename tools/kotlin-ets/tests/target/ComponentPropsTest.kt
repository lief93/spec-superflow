package dev.ets

fun checkComponentPropsContract() {
    val at = SourceSpan("Child.kt", 1, 20)
    fun literal(value: String) = EtsLiteral(value, EtsTypes.STRING, at)
    fun number(value: Int) = EtsLiteral(value, EtsTypes.NUMBER, at)
    val childType = etsClassSymbol("Child", at).type
    val self = EtsReference(EtsSymbol("child:this", "this", childType, at, true))
    val label = EtsField(EtsSymbol("child:label", "label", EtsTypes.STRING, at), literal("initial"), prop = true, watch = "changed")
    val action = EtsField(EtsSymbol("child:action", "action", EtsFunctionType(emptyList(), EtsTypes.VOID), at),
        prop = true, required = true)
    val changes = EtsField(EtsSymbol("child:changes", "changes", EtsTypes.NUMBER, at), number(0), state = true)
    fun member(field: EtsField) = EtsMember(self, field.symbol.name, field.symbol.type, at)
    fun native(name: String, arguments: List<EtsExpression>, children: List<EtsStatement>? = null) = EtsUiElement(EtsCall(
        EtsReference(EtsSymbol("native:$name", name, EtsFunctionType(arguments.map { it.type }, EtsTypes.VOID), at, true)),
        arguments, EtsTypes.VOID, at), children)
    val changed = EtsFunction("changed", emptyList(), EtsTypes.VOID, listOf(EtsExpressionStatement(EtsAssignment(
        member(changes), EtsBinary("+", member(changes), number(1), EtsTypes.NUMBER, at), at))), at, kind = EtsFunctionKind.METHOD)
    val childBuild = EtsFunction("build", emptyList(), EtsTypes.VOID, listOf(native("Column", emptyList(), listOf(
        native("Text", listOf(member(label))), native("Text", listOf(EtsBinary("+", literal("changes="), member(changes), EtsTypes.STRING, at)))
    ))), at, kind = EtsFunctionKind.METHOD, build = true)
    val child = EtsClass("Child", listOf(label, action, changes, changed, childBuild), at, component = true, exported = true)
    val pageAt = SourceSpan("Page.kt", 1, 20)
    val pageSelf = EtsReference(EtsSymbol("page:this", "this", etsClassSymbol("Page", pageAt).type, pageAt, true))
    val message = EtsField(EtsSymbol("page:message", "message", EtsTypes.STRING, pageAt), literal("first"), state = true)
    val messageValue = EtsMember(pageSelf, "message", EtsTypes.STRING, pageAt)
    val callback = EtsLambda(emptyList(), listOf(EtsExpressionStatement(EtsAssignment(messageValue, literal("second"), pageAt))), EtsTypes.VOID, pageAt)
    val invocation = EtsUiComponent(EtsReference(child.symbol), mapOf("label" to messageValue, "action" to callback))
    val click = EtsCall(EtsReference(EtsSymbol("native:onClick", "onClick", EtsFunctionType(listOf(callback.type), EtsTypes.VOID), at, true)), listOf(callback), EtsTypes.VOID, at)
    val pageBuild = EtsFunction("build", emptyList(), EtsTypes.VOID, listOf(native("Column", emptyList(), listOf(
        invocation, native("Button", listOf(literal("Change"))).copy(attributes = listOf(click))
    ))), pageAt, kind = EtsFunctionKind.METHOD, build = true)
    val page = EtsClass("Page", listOf(message, pageBuild), pageAt, entry = true, component = true)
    fun program(component: EtsClass = child, caller: EtsDeclaration = page) = EtsProgram(listOf(
        EtsFile("Child.kt", listOf(component)), EtsFile("Page.kt", listOf(caller))))
    val code = EtsPrinter().program(program())
    check("@Prop @Watch(\"changed\") label: string = \"initial\"" in code)
    check("@Require @BuilderParam action: (() => void);" in code)
    check("Child({ label: this.message, action: ()" in code)
    var sawDependency = false
    walkEts(page) { if (it is EtsReference && it.symbol == child.symbol) sawDependency = true }
    check(sawDependency)
    fun rejected(component: EtsClass = child, caller: EtsDeclaration = page) {
        check(runCatching { EtsValidator().validate(program(component, caller)) }.exceptionOrNull() is InvalidTarget)
    }
    fun withLabel(field: EtsField) = child.copy(members = listOf(field, action, changes, changed, childBuild))
    for (field in listOf(label.copy(initializer = null), label.copy(state = true), label.copy(static = true),
        label.copy(readonly = true), label.copy(visibility = EtsVisibility.PRIVATE),
        label.copy(prop = false), label.copy(watch = "missing"))) rejected(withLabel(field))
    rejected(child.copy(component = false))
    rejected(child.copy(entry = true))
    rejected(child.copy(members = listOf(label, action, changes, changed.copy(returnType = EtsTypes.NUMBER), childBuild)))
    rejected(child.copy(members = listOf(label, action.copy(prop = false), changes, changed, childBuild)))
    fun withCall(call: EtsUiComponent) = page.copy(members = listOf(message, pageBuild.copy(body = listOf(call))))
    rejected(caller = withCall(invocation.copy(properties = mapOf("label" to number(1)))))
    rejected(caller = withCall(invocation.copy(properties = mapOf("changes" to number(1)))))
    rejected(caller = withCall(invocation.copy(properties = mapOf("label" to messageValue))))
    rejected(caller = withCall(invocation.copy(component = EtsReference(child.symbol.copy(id = "missing")))))
    rejected(caller = EtsFunction("ordinary", emptyList(), EtsTypes.VOID, listOf(invocation), pageAt))
    EtsValidator().validate(program(caller = withCall(invocation.copy(properties = mapOf("action" to callback)))))
    val named = changed.copy(parameters = listOf(EtsParameter(EtsSymbol("changed:name", "name", EtsTypes.STRING, at))))
    EtsValidator().validate(program(child.copy(members = listOf(label, action, changes, named, childBuild))))
    System.getenv("KOTLIN_ETS_COMPONENT_FIXTURE")?.let { java.io.File(it).writeText(code) }
    println("Component props: typed bindings, required props, dependency traversal and observers passed")
}
