package boundedreceivers

fun main() {
    for (seed in listOf(0, -3, 7, Int.MIN_VALUE, Int.MAX_VALUE)) {
        println(interfaceCase(seed))
        println(classCase(seed))
        println(plainCase(seed))
        println(ancestorCase(seed))
        println(chainCase(seed))
        println(identityCase(seed))
        println(selfCase(seed))
        println(orderCase(seed))
    }
}
