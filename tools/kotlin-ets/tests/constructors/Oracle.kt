package constructorfixture

fun main() {
    for (seed in listOf(0, -3, 7, Int.MIN_VALUE, Int.MAX_VALUE)) {
        println(construct(seed))
        println(generic(seed))
        println(inherited(seed))
        println(captured(seed))
        println(defaults(seed))
        println(privateChain(seed))
        println(reference(seed))
        println(nativeRoot(seed))
        println(genericRoot(seed))
        println(inheritedRoot(seed))
        println(privateRoot(seed))
        val trace = Trace()
        try {
            failure(trace, seed)
            println("ok:${trace.value}")
        } catch (e: ArithmeticException) {
            println("error:${trace.value}")
        }
    }
}
