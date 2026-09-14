package captureconstruction

fun main() {
    for (seed in listOf(0, -3, 7, Int.MIN_VALUE, Int.MAX_VALUE)) {
        println(localChain(seed))
        println(localRoot(seed))
        println(innerChain(seed))
        println(innerRoot(seed))
        println(initializer(seed))
        println(collision(seed))
        println(localDispatch(seed))
        println(combined(seed))
    }
}
