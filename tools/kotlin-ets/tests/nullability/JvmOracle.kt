package nullabilityfixture

fun main() {
    for (value in listOf(null, -1, 0, 1, Int.MIN_VALUE, Int.MAX_VALUE)) {
        println(positive(value))
        println(elvisInt(value, 7))
        println(nonNullElse(value))
        println(assignedInt(value))
        println(receiverCase(value))
        println(elvisEffects(value))
        println(guardEffects(value))
    }
    for (value in listOf(null, "", "abc")) {
        println(optionalLength(value))
        println(safeLength(value))
        println(safeString(value))
        println(nonEmpty(value))
        println(safeEffects(value))
    }
}
