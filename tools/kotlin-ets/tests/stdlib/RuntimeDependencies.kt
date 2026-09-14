package dev.ets.tests.stdlib

import dev.ets.*

private val source = SourceSpan("dependencies.kt", 1, 2)
private val number = EtsLiteral(1, EtsTypes.NUMBER, source)
private val truth = EtsLiteral(true, EtsTypes.BOOLEAN, source)
private fun symbol(name: String) = EtsSymbol(name, name, EtsTypes.NUMBER, source)
private fun reference(name: String) = EtsReference(EtsSymbol("stdlib:$name", name,
    EtsFunctionType(listOf(EtsTypes.NUMBER, EtsTypes.NUMBER), EtsTypes.NUMBER), source, external = true))
private val division = EtsCall(reference("__etsIntDiv"), listOf(number, number), EtsTypes.NUMBER, source)
private fun statement(expression: EtsExpression) = EtsExpressionStatement(expression)
private fun function(body: List<EtsStatement>, parameters: List<EtsParameter> = emptyList()) =
    EtsFunction("test", parameters, EtsTypes.VOID, body, source)
private fun program(vararg declarations: EtsDeclaration) =
    EtsProgram(listOf(EtsFile("dependencies.kt", declarations.toList())))

fun main() {
    val expected = standardLibrarySupportLines(program(function(listOf(statement(division)))))
    check(expected.isNotEmpty())
    check(standardLibrarySupportLines(EtsProgram(emptyList())).isEmpty())
    val expressions = listOf<EtsExpression>(
        division,
        reference("__etsIntDiv"),
        EtsMember(division, "toString", EtsTypes.STRING, source),
        EtsCall(EtsReference(EtsSymbol("foreign", "foreign", EtsFunctionType(listOf(EtsTypes.NUMBER),
            EtsTypes.NUMBER), source, external = true)), listOf(division), EtsTypes.NUMBER, source),
        EtsNew(EtsNamedType("Box"), listOf(division), source),
        EtsBinary("+", number, division, EtsTypes.NUMBER, source),
        EtsBinary("+", division, number, EtsTypes.NUMBER, source),
        EtsUnary("-", division, EtsTypes.NUMBER, source),
        EtsConditional(division, number, number, EtsTypes.NUMBER, source),
        EtsConditional(truth, division, number, EtsTypes.NUMBER, source),
        EtsConditional(truth, number, division, EtsTypes.NUMBER, source),
        EtsAssignment(EtsReference(symbol("x")), division, source),
        EtsAssignment(EtsMember(division, "value", EtsTypes.NUMBER, source), number, source),
        EtsCast(division, EtsTypes.NUMBER, source),
        EtsArray(listOf(division), EtsTypes.NUMBER, source),
        EtsLambda(emptyList(), listOf(EtsReturn(division, source)), EtsTypes.NUMBER, source),
        EtsLambda(listOf(EtsParameter(symbol("x"), division)), emptyList(), EtsTypes.VOID, source),
    )
    val statements = expressions.map(::statement) + listOf(
        EtsVariable(symbol("x"), division, false),
        EtsReturn(division, source),
        EtsThrow(division, source),
        EtsBlock(listOf(statement(division)), source),
        EtsIf(listOf(EtsBranch(division, emptyList())), source),
        EtsIf(listOf(EtsBranch(null, listOf(statement(division)))), source),
        EtsLoop("loop", division, emptyList(), false, source),
        EtsLoop("loop", truth, listOf(statement(division)), true, source),
        function(listOf(statement(division))),
    )
    for ((index, body) in statements.withIndex()) {
        check(standardLibrarySupportLines(program(function(listOf(body)))) == expected) { "statement path $index" }
    }
    check(standardLibrarySupportLines(program(function(emptyList(),
        listOf(EtsParameter(symbol("x"), division))))) == expected)
    check(standardLibrarySupportLines(program(EtsClass("Box",
        listOf(EtsField(symbol("value"), division)), source))) == expected)
    for (kind in EtsFunctionKind.entries) {
        check(standardLibrarySupportLines(program(EtsClass("Box",
            listOf(function(listOf(statement(division))).copy(kind = kind)), source))) == expected) { "$kind body" }
    }
    val independent = reference("__etsIntRem")
    val transitive = reference("__etsSubstringFrom")
    val roots = listOf(statement(independent), statement(transitive), statement(division), statement(division))
    val forward = standardLibrarySupportLines(program(function(roots)))
    val reversed = standardLibrarySupportLines(program(function(roots.reversed())))
    check(forward == reversed) { "reference discovery order changed runtime order" }
    val multiFile = EtsProgram(listOf(
        EtsFile("one.kt", listOf(function(roots.take(2)))),
        EtsFile("two.kt", listOf(function(roots.drop(2)))),
    ))
    check(standardLibrarySupportLines(multiFile) == forward)
    check(standardLibrarySupportLines(multiFile.copy(files = multiFile.files.reversed())) == forward)
    check(forward.count { it.startsWith("function __etsIntDiv(") } == 1)
    check(forward.indexOfFirst { it.startsWith("function __etsSubstring(") } <
        forward.indexOfFirst { it.startsWith("function __etsSubstringFrom(") })
    val ignored = listOf<EtsExpression>(
        EtsLiteral("__etsIntDiv", EtsTypes.STRING, source),
        EtsUndefined(source),
        EtsReference(reference("__etsIntDiv").symbol.copy(external = false)),
        EtsReference(reference("__etsIntDiv").symbol.copy(id = "user:__etsIntDiv")),
        EtsReference(EtsSymbol("stdlib:Math", "Math", EtsNamedType("Math"), source, external = true)),
    )
    check(standardLibrarySupportLines(program(function(ignored.map(::statement) +
        listOf(EtsVariable(symbol("x"), null, false), EtsReturn(null, source), EtsJump("loop", false, source)))))
        .isEmpty())
    for (invalid in listOf(reference("__etsMissing"),
        EtsReference(reference("__etsIntDiv").symbol.copy(name = "unbound")))) {
        check(runCatching { standardLibrarySupportLines(program(function(listOf(statement(invalid))))) }.isFailure)
    }
    check(standardLibrarySupportLines(program(function(emptyList()))).isEmpty()) { "state leaked across programs" }
    val helpers = listOf("__etsIntDiv", "__etsIntRem", "__etsListGet", "__etsListAdd", "__etsListMap",
        "__etsListFilter", "__etsIllegalArgumentException", "__etsProgressionLastElement",
        "__etsSubstring", "__etsSubstringFrom", "__etsArrayIterator", "__etsArrayGet", "__etsArraySet",
        "__etsIntProgressionCreate", "__etsIntUntil", "__etsIntStep", "__etsIntReverse", "__etsProgressionIterator",
        "__etsListAny", "__etsListCount")
    val compatibility = standardLibrarySupportLines()
    check(compatibility.count { it.startsWith("function __ets") } == 20) { "UI compatibility" }
    check(compatibility.count { it.startsWith("class __ets") } == 2)
    check(compatibility.count { it.startsWith("class __etsIterator<") } == 1)
    check(compatibility.count { it.startsWith("class __etsIntProgression ") } == 1)
    helpers.forEach { helper ->
        check(compatibility.count { it.startsWith("function $helper(") || it.startsWith("function $helper<") } == 1)
    }
    val filter = standardLibrarySupportLines(program(function(listOf(statement(reference("__etsListFilter"))))))
    check(filter.count { it.startsWith("function __ets") } == 1)
    check(filter.any { it.startsWith("function __etsListFilter<") })
    for (helper in listOf("__etsListAny", "__etsListCount")) {
        val selected = standardLibrarySupportLines(program(function(listOf(statement(reference(helper))))))
        check(selected.count { it.startsWith("function __ets") } == 2)
        check(selected.count { it.startsWith("class __etsIterator<") } == 1)
        check(selected.indexOfFirst { it.startsWith("function __etsArrayIterator<") } <
            selected.indexOfFirst { it.startsWith("function $helper<") })
    }
    val progression = standardLibrarySupportLines(program(function(listOf(statement(reference("__etsProgressionLastElement"))))))
    check(progression.count { it.startsWith("function __ets") } == 2)
    check(progression.indexOfFirst { it.startsWith("function __etsIllegalArgumentException(") } >= 0)
    check(progression.indexOfFirst { it.startsWith("function __etsIllegalArgumentException(") } <
        progression.indexOfFirst { it.startsWith("function __etsProgressionLastElement(") })
    val complete = program(function(listOf(statement(division))))
    val seen = mutableListOf<EtsProgram>()
    val runtime = EtsRuntimeSupport { tree ->
        seen.add(tree)
        StandardLibraryRuntime.declarations(tree)
    }
    val single = emitEtsProgram(complete, runtime)
    val modules = emitEtsModules(complete, runtime)
    check(seen == listOf(complete, complete))
    check(single.contains("function __etsIntDiv"))
    check(modules.getValue("dependencies.ets").contains("function __etsIntDiv"))
    check(!single.contains("function __etsIntRem"))
    seen.clear()
    val malformed = program(function(listOf(EtsReturn(number, source))))
    check(runCatching { emitEtsProgram(malformed, runtime) }.exceptionOrNull() is InvalidTarget)
    check(runCatching { emitEtsModules(malformed, runtime) }.exceptionOrNull() is InvalidTarget)
    check(seen.isEmpty()) { "Invalid targets reached the runtime provider" }
    println("PASS shared runtime provider, single/multi-file output, validation before emission")
    println("PASS: ${statements.size} statement/expression paths, ${EtsFunctionKind.entries.size} function kinds, defaults/fields, identities, closure, deterministic multi-file output, fail-closed, UI compatibility")
}
