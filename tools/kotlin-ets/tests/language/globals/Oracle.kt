package globals

fun main() {
    repeat(2) {
        reset()
        println(snapshot())
        println(spacing())
        for (step in listOf(1, 1, 2, -1, 7)) {
            println(advance(4, step))
            println(snapshot())
        }
        clearSelection()
        println(snapshot())
    }
}
