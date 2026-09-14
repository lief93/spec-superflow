package dev.ets.tests.backend

fun main() {
    println(listOf(0, 3, 6).map { backendfixture.execute(it) }.joinToString(","))
    println(listOf(0, 3, 6).map { renamedfixture.evaluate(it) }.joinToString(","))
    println(listOf(backendfixture.combine(2), backendfixture.combine(2, 8, 1),
        renamedfixture.assemble(4), renamedfixture.assemble(4, 2, 3)).joinToString(","))
}
