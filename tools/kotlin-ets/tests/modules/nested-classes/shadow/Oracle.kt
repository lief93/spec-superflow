package shadowfixture

fun main() {
    for (seed in listOf(0, -3, 7, Int.MIN_VALUE, Int.MAX_VALUE)) {
        println(result(seed))
        println(localResult(seed))
        println(initializerResult(seed))
        println(laterBinding(seed))
        println(nestedResult(seed))
        println(closureResult(seed))
        println(checkedResult(seed))
        println(holderResult(seed))
        println(unshadowedResult(seed))
        println(siblingResult(seed))
        println(typeOnlyResult(seed))
    }
}
