package globals

fun advance(total: Int, step: Int = 1): String {
    currentPage = (currentPage + step) % total
    selection = currentPage
    value = currentPage + 9
    return caption + ":" + currentPage + ":" + visit()
}

fun snapshot(): String = caption + ":" + currentPage + ":" + (selection == null) + ":" + revision + ":" + value
fun spacing(extra: Int = baseGap): Int = baseGap + extra
fun clearSelection() { selection = null }
