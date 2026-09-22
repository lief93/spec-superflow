package widgetsstate

fun main() {
    var enabled = false
    var count = 0
    var label = "ready"
    fun snapshot() = listOf(enabled, count, label, if (enabled) label else "disabled").joinToString("|")
    println(snapshot())
    repeat(3) {
        enabled = !enabled
        count += 1
        label = if (enabled) "on" else "off"
        println(snapshot())
    }
}
