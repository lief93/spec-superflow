package dev.ets.tests.backend

import dev.ets.*
import java.io.File

fun main(args: Array<String>) {
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
