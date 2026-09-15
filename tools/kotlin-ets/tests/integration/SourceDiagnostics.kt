package dev.ets.tests

import dev.ets.*
import java.io.File

fun main(args: Array<String>) {
    val root = File(args.single())
    val file = root.resolve("quoted\"\t.kt")
    file.writeText("\u4E2D\uD83D\uDE00\nab\n")
    val empty = root.resolve("empty.kt").apply { writeText("") }
    val spans = listOf(
        SourceSpan(file.path, 0, 3),
        SourceSpan(file.path, 3, 6),
        SourceSpan(file.path, 7, 7),
        SourceSpan(empty.path, 0, 0),
        SourceSpan(file.path, -1, -1),
        SourceSpan(file.path, 3, 2),
        SourceSpan(file.path, 0, 8),
        SourceSpan(root.resolve("missing.kt").path, 0, 0),
        SourceSpan(root.path, 0, 0),
        SourceSpan(null, 0, 0),
    )
    spans.forEach { println(diagnosticSourceJson(it)) }
    println(quote("error\t\b\u0000\r\n\"\\"))
}
