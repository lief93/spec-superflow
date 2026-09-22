package widgetpager

fun main() {
    var currentPage = 1
    println(currentPage)
    for (page in listOf(2, 0)) {
        currentPage = page
        println(currentPage)
    }
}
