package globals

const val baseGap: Int = 8
val caption: String = "Page"
var currentPage: Int = 0
var selection: Int? = null
var value: Int = 9
private var visits: Int = 0
var revision: Int = 1
    private set

fun visit(): Int {
    visits++
    revision++
    return visits
}

fun reset() {
    currentPage = 0
    selection = null
    value = 9
    visits = 0
    revision = 1
}
