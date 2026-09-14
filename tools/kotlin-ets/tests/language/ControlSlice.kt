package languagefixture

fun controlSlice(): Int {
    var value = 0
    do {
        value++
        if (value == 3) break
    } while (value < 5)
    val callback: () -> Unit = letUnit@ {
        value += 4
        return@letUnit
    }
    callback()
    return value
}
