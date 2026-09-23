package widgetpager

fun main() {
    var currentPage = 1
    var selected = -1
    fun snapshot() = listOf(currentPage,
        if (currentPage < 3) "A" else "B",
        "Indicator ${currentPage + 1}/4",
        if (currentPage == 3) "Finish" else "Next",
        selected).joinToString("|")
    println(snapshot())
    for (page in listOf(2, 3)) {
        currentPage = page
        println(snapshot())
    }
    selected = currentPage
    println(snapshot())
    currentPage = 0
    println(snapshot())
}
