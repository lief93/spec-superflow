package dev.ets

fun main() {
    val source = SourceSpan("Arithmetic.kt", 12, 78)
    val number = EtsTypes.NUMBER
    val base = EtsSymbol("base", "base", number, source)
    val extra = EtsSymbol("extra", "extra", number, source)
    val sum = EtsBinary("+", EtsReference(base), EtsReference(extra), number, source)
    val function = EtsFunction("gap", listOf(EtsParameter(base), EtsParameter(extra, EtsLiteral(5, number, source))),
        number, listOf(EtsReturn(sum, source)), source, exported = true)
    val program = EtsProgram(listOf(EtsFile("Arithmetic.kt", listOf(function))))
    val code = EtsPrinter().program(program)
    check("export function gap(base: number, extra: number = 5)" in code)
    check("return base + extra;" in code)
    checkPrinterPrecedence()
    checkAccessorContract()
    checkConstructorFlowContract()
    checkVisibilityContract()
    checkInheritanceContract()
    checkInterfacePropertyContract()
    checkVirtualPropertyContract()
    checkGenericInheritanceContract()
    checkBoundedReceiverContract()
    checkGenericMethodContract()
    checkCovariantReturnContract()
    checkCovariantPropertyContract()
    checkDeclarationVariance()
    checkBoundConstraints()
    checkOverloadIdentityContract()
    checkClassIdentityContract()
    checkStrictBindingContract()
    checkGlobalBuilderContract()
    checkGlobalVariableContract()
    checkTryContract()
    check(sum.source == source)
    val bad = function.copy(body = listOf(EtsReturn(EtsLiteral("wrong", EtsTypes.STRING, source), source)))
    val failure = runCatching { EtsPrinter().program(program.copy(files = listOf(EtsFile("Arithmetic.kt", listOf(bad))))) }.exceptionOrNull()
    check(failure is InvalidTarget && failure.source == source) { "Wrong return type must be rejected at its source" }
    val missing = function.copy(body = listOf(EtsReturn(EtsReference(EtsSymbol("missing", "unknown", number, source)), source)))
    check(runCatching { EtsPrinter().program(EtsProgram(listOf(EtsFile("Arithmetic.kt", listOf(missing))))) }.exceptionOrNull() is InvalidTarget)
    val badCondition = function.copy(body = listOf(EtsIf(listOf(EtsBranch(EtsLiteral(1, number, source), listOf(EtsReturn(sum, source)))), source)))
    check(runCatching { EtsPrinter().program(EtsProgram(listOf(EtsFile("Arithmetic.kt", listOf(badCondition))))) }.exceptionOrNull() is InvalidTarget)
    val escaped = EtsLiteral("quote\"\n\\\u2028", EtsTypes.STRING, source)
    check(EtsPrinter().expression(escaped) == "\"quote\\\"\\n\\\\\\u2028\"")
    check(EtsPrinter().program(program) == code)
    val badCall = EtsCall(EtsReference(EtsSymbol("native", "native", EtsFunctionType(listOf(number), number), source, external = true)),
        listOf(EtsLiteral("bad", EtsTypes.STRING, source)), number, source)
    check(runCatching { EtsPrinter().program(EtsProgram(listOf(EtsFile("Arithmetic.kt", listOf(function.copy(body = listOf(EtsReturn(badCall, source)))))))) }.exceptionOrNull() is InvalidTarget)
    println(code)
}

private fun checkAccessorContract() {
    val source = SourceSpan("Accessors.kt", 10, 20)
    val number = EtsTypes.NUMBER
    val parameter = EtsParameter(EtsSymbol("next", "next", number, source))
    val getter = EtsFunction("value", emptyList(), number,
        listOf(EtsReturn(EtsLiteral(3, number, source), source)), source, kind = EtsFunctionKind.GETTER)
    val setter = EtsFunction("value", listOf(parameter), EtsTypes.VOID,
        listOf(EtsReturn(null, source)), source, kind = EtsFunctionKind.SETTER)
    fun program(vararg members: EtsClassMember) = EtsProgram(listOf(EtsFile("Accessors.kt",
        listOf(EtsClass("Accessors", members.toList(), source)))))
    val code = EtsPrinter().program(program(getter, setter))
    check("get value(): number" in code)
    check("set value(next: number) {" in code)
    for (invalid in listOf(getter.copy(parameters = listOf(parameter)),
        getter.copy(returnType = EtsTypes.VOID), setter.copy(parameters = emptyList()),
        setter.copy(returnType = number), setter.copy(parameters = listOf(parameter.copy(defaultValue = EtsLiteral(1, number, source)))))) {
        val failure = runCatching { EtsPrinter().program(program(invalid)) }.exceptionOrNull()
        check(failure is InvalidTarget && failure.source == source)
    }
}

private fun checkPrinterPrecedence() {
    val source = SourceSpan("Precedence.kt", 0, 1)
    val number = EtsTypes.NUMBER
    val printer = EtsPrinter()
    fun ref(name: String) = EtsReference(EtsSymbol(name, name, number, source))
    fun binary(op: String, left: EtsExpression, right: EtsExpression) = EtsBinary(op, left, right, number, source)
    fun expect(value: EtsExpression, text: String) {
        check(printer.expression(value) == text) { "Expected $text, got ${printer.expression(value)}" }
    }
    val a = ref("a")
    val b = ref("b")
    val c = ref("c")
    expect(binary("*", binary("+", a, b), c), "(a + b) * c")
    expect(binary("+", a, binary("*", b, c)), "a + b * c")
    expect(binary("-", a, binary("-", b, c)), "a - (b - c)")
    expect(binary("/", a, binary("*", b, c)), "a / (b * c)")
    expect(binary("+", a, binary("+", b, c)), "a + (b + c)")
    expect(binary("|", binary("+", a, b), c), "a + b | c")
    expect(binary("+", binary("|", a, b), c), "(a | b) + c")
    expect(binary("??", binary("||", a, b), c), "(a || b) ?? c")
    expect(binary("||", a, binary("??", b, c)), "a || (b ?? c)")
    expect(binary("??", a, binary("&&", b, c)), "a ?? (b && c)")
    expect(EtsMember(a, "value", number, source), "a.value")
    expect(EtsMember(EtsLiteral(16, number, source), "value", number, source), "(16).value")
    expect(EtsMember(EtsLiteral(-1, number, source), "value", number, source), "(-1).value")
    expect(EtsCall(EtsMember(a, "read", EtsFunctionType(listOf(number), number), source), listOf(b), number, source), "a.read(b)")
    expect(EtsMember(EtsCast(a, EtsNamedType("Box"), source), "value", number, source), "(a as Box).value")
    expect(binary("|", EtsCast(a, number, source), b), "(a as number) | b")
    expect(EtsConditional(EtsConditional(a, b, c, number, source), b, c, number, source), "(a ? b : c) ? b : c")
    expect(EtsAssignment(a, EtsAssignment(b, c, source), source), "a = b = c")
    expect(EtsUnary("-", EtsUnary("-", a, number, source), number, source), "- - a")
    val lambda = EtsLambda(emptyList(), listOf(EtsReturn(a, source)), number, source)
    expect(EtsCall(lambda, emptyList(), number, source), "((): number => {\n  return a;\n})()")
}
