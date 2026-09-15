package computed

fun main() {
    println(initialSnapshot())
    for (value in listOf(-3, 0, 1, 2, 5, 12)) {
        for (extra in listOf(-2, 0, 3)) {
            println(readTwice(value))
            println(update(value, extra))
            println(setOnly(extra))
            println(storedAccess(value, extra))
        }
    }
}
