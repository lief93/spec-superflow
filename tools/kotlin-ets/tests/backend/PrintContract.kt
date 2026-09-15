package dev.ets.tests.backend

import dev.ets.*
import java.io.File

fun main(args: Array<String>) {
    val source = SourceSpan("printer-test", 0, 1)
    val symbol = EtsSymbol("box", "Box", EtsFunctionType(emptyList(), EtsTypes.VOID), source, external = true)
    val leaf = EtsUiElement(EtsCall(EtsReference(symbol), emptyList(), EtsTypes.VOID, source))
    val ui = listOf(leaf, leaf.copy(children = emptyList()), leaf.copy(children = listOf(leaf)))
    check(EtsPrinter().statements(ui) == listOf("Box()", "Box() {}", "Box() {", "  Box()", "}"))
    check(leaf.children == null)
    args.drop(2).forEach { path ->
        val program = lowerFixture(File(path).canonicalPath, args[0], verify = false)
        val before = program.toString()
        val printer = EtsPrinter()
        val first = printer.program(program)
        repeat(10) {
            check(printer.program(program) == first)
            check(EtsPrinter().program(program) == first)
            check(program.toString() == before) { "Printer mutated its AST" }
        }
        File(args[1], File(path).nameWithoutExtension + ".ets").writeText(first)
    }
    println("PASS repeated same-AST printing is deterministic and non-mutating")
}
