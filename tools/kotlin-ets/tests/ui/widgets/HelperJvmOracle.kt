package widgethelpers

fun main() {
    val effects = mutableListOf<String>()
    val title = "title"
    val label = "slot"
    val enabled = true
    effects += "title:$title"
    if (enabled) effects += "action"
    effects += "content:$label"
    println(effects.joinToString("|"))
}
