package dev.ets.tests.stdlib

import dev.ets.*

fun main() {
    val source = SourceSpan("quantifier-runtime.kt", 0, 1)
    val element = EtsTypes.NUMBER
    val parameters = listOf(EtsNamedType("Array", listOf(element)), EtsFunctionType(listOf(element), EtsTypes.BOOLEAN))
    val references = listOf("__etsListAny" to EtsFunctionType(parameters + EtsTypes.BOOLEAN, EtsTypes.BOOLEAN),
        "__etsListCount" to EtsFunctionType(parameters, EtsTypes.NUMBER)).map { (name, type) ->
        EtsExpressionStatement(EtsReference(EtsSymbol("stdlib:$name", name, type, source, external = true)))
    }
    val program = EtsProgram(listOf(EtsFile("runtime.kt", listOf(
        EtsFunction("probe", emptyList(), EtsTypes.VOID, references, source)))))
    println(StandardLibraryRuntime.declarations(program).joinToString("\n"))
}
