package nestedobjects

fun observations(): List<String> {
    val before = initialized
    val first = First.label(5)
    val second = Second.label(7)
    First.Settings.value += 4
    return listOf("$before", first, second, First.label(9),
        "${First.Companion === First.Companion}:${First.Settings.value}:$initialized",
        "${State.select(false).name}:${State.select(true).ordinal}")
}
