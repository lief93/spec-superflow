package enums

fun observations(): List<String> {
    val before = trace
    val stage = selected()
    val values = Stage.values()
    values[0] = Stage.LAST
    return listOf(
        "${stage.name}:${stage.ordinal}:${stage.code}:${stage.label("go:")}",
        "${stage == Stage.SECOND}:${stage === lookup("SECOND")}:${stage != Stage.FIRST}",
        "${choose(Stage.FIRST)}:${choose(stage)}:${choose(Stage.LAST)}",
        "${Stage.values()[0].name}:${values[0].name}",
        "${Stage.entries.size}:${Stage.entries[2].name}",
        "${stage.hashCode() == selected().hashCode()}:${stage.toString()}",
        "$before:$trace:${Stage.entries === Stage.entries}:${stage.label()}"
    )
}

fun unknown(): Stage = lookup("MISSING")
fun broken(): Broken = Broken.ENTRY
