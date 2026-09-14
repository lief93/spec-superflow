package accessorfixture

fun main() {
    for (start in listOf(0, 5, -2)) {
        for (next in listOf(-3, 0, 4)) {
            println(accessorSlice(start, next))
        }
    }
    for (start in listOf(0, 5, -2)) {
        for (next in listOf(-3, 0, 4)) {
            println(accessorUpdate(start, next))
        }
    }
}
