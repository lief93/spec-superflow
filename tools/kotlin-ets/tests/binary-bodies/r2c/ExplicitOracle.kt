package defaultconsumer

fun main() {
    for (seed in intArrayOf(1, -2, Int.MAX_VALUE)) println(explicitOnly(seed))
}
