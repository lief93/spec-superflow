package crossfileoverloads

fun main() {
    for (seed in listOf(0, -3, 7, Int.MIN_VALUE, Int.MAX_VALUE)) {
        println(crossFileCase(seed))
        println(identityCase(seed))
        val token = Token(seed)
        println(keep(token) === token)
    }
}
