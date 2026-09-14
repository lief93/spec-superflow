package genericmethods

fun main() {
    for (seed in listOf(0, -3, 7, Int.MIN_VALUE, Int.MAX_VALUE)) {
        println(controlCase(seed))
        println(interfaceCase(seed))
        println(inheritedCase(seed))
        println(substitutionsCase(seed))
        println(constraintsCase(seed))
        println(boundedCase(seed))
        println(effectsCase(seed))
    }
}
