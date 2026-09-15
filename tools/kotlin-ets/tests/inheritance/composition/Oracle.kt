package declarationcomposition

fun main() {
    for (seed in intArrayOf(0, -3, 7, Int.MIN_VALUE, Int.MAX_VALUE)) {
        println(inlineCapture(seed))
        println(localCapture(seed))
        println(substitutedCapture(seed))
        println(nestedCapture(seed))
        println(inputCapture(seed))
        println(boundCapture(seed))
    }
}
