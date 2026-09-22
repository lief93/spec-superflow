package widgetsstate

fun main() {
    val title = "Profile"
    val step = 2
    val subtitle: String? = null
    val model = "model"
    val actions = mutableListOf<String>()
    var enabled = false
    var count = 0
    var label = "ready"
    fun snapshot() = listOf(enabled, count, label,
        if (enabled) "$title:$model:$label" else "disabled",
        subtitle ?: "none", actions.joinToString(",")).joinToString("|")
    println(snapshot())
    repeat(3) {
        enabled = !enabled
        count += step
        label = if (enabled) "on" else "off"
        actions += label
        println(snapshot())
    }
}
