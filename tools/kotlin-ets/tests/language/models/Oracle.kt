package models

fun main() {
    println(emptinessCheck(false))
    println(emptinessCheck(true))
    println(evaluationOrder())
    println(nullableLet(null))
    println(nullableLet(""))
    println(nullableLet("Title"))
    println(guardedGeneric(null))
    println(guardedGeneric("Title"))
    println(nullableGeneric(null))
    println(nullableGeneric("Title"))
    for (minimum in listOf(-1, 0, 2, 3, 7)) {
        for (extra in listOf(-2, 0, 3)) {
            for (pick in listOf(false, true)) {
                println(scenario(minimum, extra, pick))
                println(afterAdjustment(2))
            }
        }
    }
}
