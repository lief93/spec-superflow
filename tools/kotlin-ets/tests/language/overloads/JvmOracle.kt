package overloadfixture

fun main() {
    for (seed in listOf(0, -3, 7, Int.MIN_VALUE, Int.MAX_VALUE)) {
        println(arityCase(seed))
        println(numericCase(seed))
        println(memberCase(seed))
        println(genericCase(seed))
        println(classGenericCase(seed))
        println(effectsCase(seed))
    }
}
