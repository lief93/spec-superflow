package languagefixture

data class Coordinates(val x: Int, val y: Int)

fun scopeSlice(): Int {
    val (x, y) = Coordinates(2, 3)
    val tmp0_container = 5
    return x + y + tmp0_container
}
