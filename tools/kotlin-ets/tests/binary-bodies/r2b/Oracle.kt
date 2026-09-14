package extensionconsumer

fun main() {
    for (seed in intArrayOf(1, -2, Int.MAX_VALUE)) {
        val direct = Box(seed)
        val returnedDirect = directIdentity(direct)
        check(returnedDirect === direct)
        returnedDirect.value += 7
        check(direct.value == seed + 8)
        val entry = Box(seed)
        val returnedEntry = entryIdentity(entry)
        check(returnedEntry === entry && returnedEntry !== returnedDirect)
        returnedEntry.value += 7
        check(entry.value == seed + 8)
        println(scenario(seed))
    }
}
