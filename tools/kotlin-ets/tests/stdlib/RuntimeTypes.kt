package dev.ets.tests.stdlib

import dev.ets.*

private val span = SourceSpan("runtime-types.kt", 1, 2)
private val cursor = EtsNamedType("__etsIterator", listOf(EtsTypes.NUMBER), "stdlib:__etsIterator", external = true)
private val progression = EtsNamedType("__etsIntProgression", symbolId = "stdlib:__etsIntProgression", external = true)
private fun program(type: EtsType) = EtsProgram(listOf(EtsFile("runtime-types.kt", listOf(
    EtsFunction("typeOnly", listOf(EtsParameter(EtsSymbol("x", "x", type, span))), EtsTypes.VOID, emptyList(), span)))))

fun main() {
    val expected = StandardLibraryRuntime.declarations(program(cursor))
    check(expected.any { it.startsWith("class __etsIterator<") }) { "Type-only cursor did not select its runtime" }
    check(expected.none { it.startsWith("function __etsArrayIterator") })
    val wrappers = listOf<EtsType>(cursor, EtsNullableType(cursor), EtsTupleType(listOf(cursor)),
        EtsNamedType("Array", listOf(cursor)), EtsFunctionType(listOf(cursor), EtsTypes.VOID),
        EtsFunctionType(emptyList(), cursor), EtsRecordType("Options", mapOf("iterator" to cursor)))
    for (wrapper in wrappers) check(StandardLibraryRuntime.declarations(program(wrapper)) == expected)
    val heritage = EtsNamedType("SourceBase", listOf(cursor), "source:base")
    val parentPrograms = listOf(
        EtsProgram(listOf(EtsFile("runtime-types.kt", listOf(EtsClass("Child", emptyList(), span, baseClass = heritage))))),
        EtsProgram(listOf(EtsFile("runtime-types.kt", listOf(EtsClass("Child", emptyList(), span, interfaces = listOf(heritage)))))),
        EtsProgram(listOf(EtsFile("runtime-types.kt", listOf(EtsFunction("constructorProbe", emptyList(), EtsTypes.VOID,
            listOf(EtsSuperConstructorCall(heritage, emptyList(), span)), span))))),
    )
    for (parentProgram in parentPrograms) check(StandardLibraryRuntime.declarations(parentProgram) == expected) {
        "Parent/super-constructor type did not select runtime"
    }
    val p = StandardLibraryRuntime.declarations(program(progression))
    check(p.any { it.startsWith("class __etsIntProgression") })
    check(p.any { it.startsWith("function __etsProgressionLastElement") })
    check(p.any { it.startsWith("function __etsIllegalArgumentException") })
    val invalid = listOf(cursor.copy(name = "Other"), cursor.copy(arguments = emptyList()),
        cursor.copy(arguments = listOf(EtsTypes.NUMBER, EtsTypes.STRING)),
        cursor.copy(arguments = listOf(EtsTypes.VOID)), cursor.copy(external = false),
        cursor.copy(symbolId = "stdlib:unknown"), progression.copy(arguments = listOf(EtsTypes.NUMBER)))
    for (type in invalid) check(runCatching { StandardLibraryRuntime.declarations(program(type)) }.isFailure) { "Accepted $type" }
    check(StandardLibraryRuntime.declarations(program(cursor.copy(symbolId = "source:Other", external = false))).isEmpty())
    check(StandardLibraryRuntime.declarations(program(EtsNamedType("__etsIterator", listOf(EtsTypes.NUMBER)))).isEmpty())
    println("PASS type-only runtime selection, nested records/functions/tuples/nullables, identity and invalid type shapes")
}
