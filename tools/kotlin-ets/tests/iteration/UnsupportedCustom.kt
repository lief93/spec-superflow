class CustomValues : Iterable<Int> {
    override fun iterator(): Iterator<Int> = listOf(1, 2).iterator()
}
fun customValues(): Int {
    var result = 0
    for (value in CustomValues()) result += value
    return result
}
