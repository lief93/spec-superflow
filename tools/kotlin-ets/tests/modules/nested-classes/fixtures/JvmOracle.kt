package nestedfixture

fun main() {
    for (seed in listOf(0, -3, 7, Int.MIN_VALUE, Int.MAX_VALUE)) {
        println(nestedCase(seed))
        println(localCase(seed))
        println(identityCase(seed))
    }
}
